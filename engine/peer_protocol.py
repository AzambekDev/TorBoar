import asyncio
import struct
from typing import Optional
from engine.logger import log
from engine.bencoding import bencode, bdecode

# Message IDs
MSG_CHOKE = 0
MSG_UNCHOKE = 1
MSG_INTERESTED = 2
MSG_NOT_INTERESTED = 3
MSG_HAVE = 4
MSG_BITFIELD = 5
MSG_REQUEST = 6
MSG_PIECE = 7
MSG_EXTENDED = 20
class PeerConnection:
    def __init__(self, ip: str, port: int, info_hash: bytes, peer_id: bytes):
        self.ip = ip
        self.port = port
        self.info_hash = info_hash
        self.my_peer_id = peer_id
        
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        
        # State
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False
        
        self.peer_id: Optional[bytes] = None
        self.bitfield: bytearray = bytearray()
        
        # Extensions
        self.supports_extensions = False
        self.peer_ut_metadata_id: Optional[int] = None
        self.metadata_size: int = 0
        
        self.connected = False

    async def connect(self, timeout=10) -> bool:
        try:
            fut = asyncio.open_connection(self.ip, self.port)
            self.reader, self.writer = await asyncio.wait_for(fut, timeout=timeout)
            self.connected = True
            log(f"[Peer {self.ip}] TCP Connection established.")
            return True
        except Exception as e:
            # Normal in BitTorrent for peers to be offline/unreachable
            # print(f"Failed to connect to {self.ip}:{self.port}: {e}")
            return False

    async def handshake(self, timeout=10) -> bool:
        if not self.connected:
            return False
            
        pstr = b"BitTorrent protocol"
        pstrlen = bytes([len(pstr)])
        reserved = bytearray(b"\x00" * 8)
        reserved[5] |= 0x10  # Set 20th bit from right to signal extension support

        
        handshake_msg = pstrlen + pstr + reserved + self.info_hash + self.my_peer_id
        
        try:
            log(f"[Peer {self.ip}] Sending BitTorrent handshake...")
            self.writer.write(handshake_msg)
            await self.writer.drain()
            
            # Read handshake response
            response = await asyncio.wait_for(self.reader.readexactly(68), timeout=timeout)
            pstrlen_int = response[0]
            
            if pstrlen_int != len(pstr):
                return False
                
            response_pstr = response[1:20]
            if response_pstr != pstr:
                return False
                
            _reserved = response[20:28]
            response_info_hash = response[28:48]
            
            if response_info_hash != self.info_hash:
                log(f"[Peer {self.ip}] Info hash mismatch in handshake.")
                return False
                
            self.peer_id = response[48:68]
            log(f"[Peer {self.ip}] Handshake successful.")
            
            # Check if peer supports extensions
            if _reserved[5] & 0x10:
                self.supports_extensions = True
                
            return True
            
        except Exception as e:
            # print(f"Handshake failed with {self.ip}: {e}")
            return False

    async def send_message(self, msg_id: int, payload: bytes = b""):
        if not self.connected:
            return
        length = struct.pack(">I", 1 + len(payload))
        msg = length + bytes([msg_id]) + payload
        try:
            self.writer.write(msg)
            await self.writer.drain()
        except Exception as e:
            print(f"Error sending message to {self.ip}: {e}")
            self.disconnect()

    async def send_keep_alive(self):
        if not self.connected:
            return
        try:
            self.writer.write(struct.pack(">I", 0))
            await self.writer.drain()
        except Exception as e:
            print(f"Error sending keep-alive to {self.ip}: {e}")
            self.disconnect()

    async def send_interested(self):
        self.am_interested = True
        await self.send_message(MSG_INTERESTED)
        
    async def send_request(self, index: int, begin: int, length: int):
        payload = struct.pack(">III", index, begin, length)
        await self.send_message(MSG_REQUEST, payload)

    async def receive_message(self) -> tuple[int, bytes]:
        """Returns (msg_id, payload). If keep-alive, returns (-1, b'')."""
        if not self.connected:
            raise ConnectionError("Not connected")
            
        length_bytes = await self.reader.readexactly(4)
        length = struct.unpack(">I", length_bytes)[0]
        
        if length == 0:
            return -1, b"" # Keep-alive
            
        msg_id_bytes = await self.reader.readexactly(1)
        msg_id = msg_id_bytes[0]
        
        payload = b""
        if length > 1:
            payload = await self.reader.readexactly(length - 1)
            
        return msg_id, payload

    def disconnect(self):
        if self.writer:
            self.writer.close()
        self.connected = False

    async def send_extended_handshake(self, local_ut_metadata_id: int):
        if not self.connected or not self.supports_extensions:
            return
            
        payload_dict = {
            b'm': {
                b'ut_metadata': local_ut_metadata_id
            }
        }
        
        # Extension handshake has extended msg id 0
        payload = bytes([0]) + bencode(payload_dict)
        await self.send_message(MSG_EXTENDED, payload)

    def parse_extended_handshake(self, payload: bytes):
        if len(payload) < 2 or payload[0] != 0:
            return
            
        try:
            bencoded_dict, _, _ = bdecode(payload[1:])
            if isinstance(bencoded_dict, dict):
                m = bencoded_dict.get(b'm')
                if isinstance(m, dict):
                    self.peer_ut_metadata_id = m.get(b'ut_metadata')
                self.metadata_size = bencoded_dict.get(b'metadata_size', 0)
        except Exception as e:
            log(f"Failed to parse extended handshake. Payload preview: {payload[:20].hex()} | Error: {e}")

    async def send_metadata_request(self, piece_index: int):
        if not self.connected or self.peer_ut_metadata_id is None:
            return
            
        payload_dict = {
            b'msg_type': 0, # 0 = request
            b'piece': piece_index
        }
        
        payload = bytes([self.peer_ut_metadata_id]) + bencode(payload_dict)
        await self.send_message(MSG_EXTENDED, payload)

    def parse_metadata_message(self, payload: bytes) -> tuple[Optional[int], Optional[int], Optional[bytes]]:
        """Parses ut_metadata payload. Returns (msg_type, piece_index, raw_data)."""
        if not payload:
            return None, None, None
            
        try:
            bencoded_dict, _, consumed = bdecode(payload)
            if not isinstance(bencoded_dict, dict):
                return None, None, None
                
            msg_type = bencoded_dict.get(b'msg_type')
            piece = bencoded_dict.get(b'piece')
            
            raw_data = payload[consumed:]
            
            return msg_type, piece, raw_data
        except Exception:
            return None, None, None
