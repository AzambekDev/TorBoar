import asyncio
import hashlib
import os
import struct
import concurrent.futures
import threading
from typing import List, Dict, Set
from engine.torrent_file import TorrentFile
from engine.magnet import MagnetLink
from engine.peer_protocol import PeerConnection, MSG_REQUEST, MSG_PIECE, MSG_HAVE, MSG_BITFIELD, MSG_INTERESTED, MSG_EXTENDED, MSG_CHOKE, MSG_UNCHOKE
from engine.bencoding import bencode, bdecode
from engine.logger import log

BLOCK_SIZE = 16384 # 16 KiB

class Piece:
    def __init__(self, index: int, length: int, expected_hash: bytes):
        self.index = index
        self.length = length
        self.expected_hash = expected_hash
        self.blocks_count = (length + BLOCK_SIZE - 1) // BLOCK_SIZE
        self.blocks: Dict[int, bytes] = {} # offset -> data
        self.requested_blocks: Set[int] = set()
        self.completed = False
        self.fully_requested = False

    def get_missing_blocks(self) -> List[int]:
        if self.completed or getattr(self, 'fully_requested', False):
            return []
        missing = []
        for i in range(self.blocks_count):
            offset = i * BLOCK_SIZE
            if offset not in self.blocks and offset not in self.requested_blocks:
                missing.append(offset)
        if not missing:
            self.fully_requested = True
        return missing
        
    def add_block(self, offset: int, data: bytes):
        if self.completed or getattr(self, 'verifying', False):
            return
        self.blocks[offset] = data
        if offset in self.requested_blocks:
            self.requested_blocks.remove(offset)
            
    def is_complete(self) -> bool:
        if self.completed:
            return True
        total_received = sum(len(b) for b in self.blocks.values())
        return total_received == self.length
        
    def get_data(self) -> bytes:
        data = bytearray()
        for offset in sorted(self.blocks.keys()):
            data.extend(self.blocks[offset])
        return bytes(data)

    def verify(self) -> bool:
        if not self.is_complete():
            return False
            
        data = bytearray()
        for offset in sorted(self.blocks.keys()):
            data.extend(self.blocks[offset])
            
        sha1 = hashlib.sha1()
        sha1.update(data)
        
        if sha1.digest() == self.expected_hash:
            self.completed = True
            return True
        else:
            self.blocks.clear()
            self.requested_blocks.clear()
            return False
            
class DownloadManager:
    def __init__(self, target, save_path: str):
        self.save_path = save_path
        self.torrent = None
        self.magnet = None
        
        self.downloaded = 0
        self.uploaded = 0
        self.down_speed = 0
        self.up_speed = 0
        
        self.bytes_downloaded_window = 0
        self.bytes_uploaded_window = 0
        
        self.active_peers: List[PeerConnection] = []
        self.pending_peers: List[PeerConnection] = []
        self.seen_ips: Set[str] = set()
        self.completed_pieces: Set[int] = set()
        self.incomplete_pieces: List[Piece] = []
        self.is_running = False
        self.sequential_mode = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        self.disk_lock = threading.Lock()
        
        # Metadata Fetching State
        self.fetching_metadata = False
        self.metadata_buffer: Dict[int, bytes] = {}
        self.metadata_requested: Set[int] = set()
        self.metadata_size = 0
        
        if isinstance(target, TorrentFile):
            self.torrent = target
            self.pieces: List[Piece] = []
            self._init_pieces()
        elif isinstance(target, MagnetLink):
            self.magnet = target
            self.fetching_metadata = True
            self.pieces = []
            self.incomplete_pieces = []
        else:
            raise ValueError("Target must be TorrentFile or MagnetLink")

    def _create_sparse_file(self):
        file_info = self.torrent.files[0]
        full_path = os.path.join(self.save_path, file_info['path'])
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        if not os.path.exists(full_path):
            with open(full_path, 'wb') as f:
                pass # Create empty file
                
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                
                GENERIC_READ = 0x80000000
                GENERIC_WRITE = 0x40000000
                OPEN_EXISTING = 3
                FSCTL_SET_SPARSE = 590020
                
                try:
                    handle = ctypes.windll.kernel32.CreateFileW(
                        full_path,
                        GENERIC_READ | GENERIC_WRITE,
                        3, # FILE_SHARE_READ | FILE_SHARE_WRITE
                        None,
                        OPEN_EXISTING,
                        0x80, # FILE_ATTRIBUTE_NORMAL
                        None
                    )
                    
                    if handle not in (0, -1, 4294967295):
                        bytes_returned = wintypes.DWORD()
                        ctypes.windll.kernel32.DeviceIoControl(
                            handle,
                            FSCTL_SET_SPARSE,
                            None, 0,
                            None, 0,
                            ctypes.byref(bytes_returned),
                            None
                        )
                        ctypes.windll.kernel32.CloseHandle(handle)
                except Exception as e:
                    log(f"Failed to set sparse file: {e}")

    def _init_pieces(self):
        self._create_sparse_file()
        num_pieces = len(self.torrent.pieces) // 20
        for i in range(num_pieces):
            hash_bytes = self.torrent.pieces[i*20:(i+1)*20]
            if i == num_pieces - 1:
                length = self.torrent.total_size % self.torrent.piece_length
                if length == 0:
                    length = self.torrent.piece_length
            else:
                length = self.torrent.piece_length
            new_piece = Piece(i, length, hash_bytes)
            self.pieces.append(new_piece)
            self.incomplete_pieces.append(new_piece)

    def write_piece_to_disk(self, piece: Piece):
        # Basic single-file writer for now
        file_info = self.torrent.files[0]
        full_path = os.path.join(self.save_path, file_info['path'])
        
        with self.disk_lock:
            with open(full_path, 'r+b') as f:
                f.seek(piece.index * self.torrent.piece_length)
                f.write(piece.get_data())
            
        # Update downloaded bytes
        self.downloaded += piece.length

    def broadcast_have(self, index: int):
        payload = struct.pack(">I", index)
        for peer in self.active_peers:
            if peer.connected:
                asyncio.create_task(peer.send_message(MSG_HAVE, payload))

    def _handle_metadata_piece(self, piece: int, data: bytes):
        if not self.fetching_metadata or self.metadata_size == 0:
            return
            
        self.metadata_buffer[piece] = data
        
        current_size = sum(len(b) for b in self.metadata_buffer.values())
        if current_size < self.metadata_size:
            return # Still missing pieces
            
        assembled = bytearray()
        for i in range(len(self.metadata_buffer)):
            if i not in self.metadata_buffer:
                return # Still missing pieces
            assembled.extend(self.metadata_buffer[i])
            
        # Verify hash
        sha1 = hashlib.sha1()
        sha1.update(assembled)
        
        if sha1.digest() == self.magnet.info_hash:
            log("Metadata successfully retrieved and verified!")
            self.fetching_metadata = False
            self.torrent = TorrentFile(info_raw=bytes(assembled))
            if not self.torrent.name:
                self.torrent.name = self.magnet.name
            self._init_pieces()
        else:
            log("Metadata hash mismatch, discarding.")
            self.metadata_buffer.clear()
            self.metadata_requested.clear()

    async def _handle_piece_block(self, index: int, begin: int, data: bytes):
        if index < 0 or index >= len(self.pieces):
            return
        piece = self.pieces[index]
        piece.add_block(begin, data)
        self.bytes_downloaded_window += len(data)
        
        if piece.is_complete() and not getattr(piece, 'verifying', False) and index not in self.completed_pieces:
            piece.verifying = True
            loop = asyncio.get_running_loop()
            
            def verify_and_write():
                if piece.verify():
                    self.write_piece_to_disk(piece)
                    return True
                else:
                    piece.verifying = False
                    return False
                    
            success = await loop.run_in_executor(self.executor, verify_and_write)
            
            if success:
                log(f"Piece {index} completed and verified!")
                self.completed_pieces.add(index)
                if piece in self.incomplete_pieces:
                    self.incomplete_pieces.remove(piece)
                log(f"Piece {index} saved to disk.")
                self.broadcast_have(index)
            else:
                log(f"Piece {index} failed hash check.")

    async def _request_blocks(self, peer: PeerConnection):
        if not peer.bitfield or len(self.incomplete_pieces) == 0:
            return
            
        if peer.pending_requests >= 250: # Increased aggressive pipelining limit
            return
            
        # Avoid O(N) bottleneck by starting from where this peer left off
        start_idx = getattr(peer, 'last_piece_scan_idx', 0)
        total_pieces = len(self.incomplete_pieces)
        if start_idx >= total_pieces:
            start_idx = 0
            
        checked_count = 0
        while checked_count < total_pieces:
            piece = self.incomplete_pieces[start_idx]
            checked_count += 1
            
            if not getattr(piece, 'verifying', False) and not getattr(piece, 'fully_requested', False):
                byte_idx = piece.index // 8
                bit_idx = 7 - (piece.index % 8)
                if byte_idx < len(peer.bitfield) and (peer.bitfield[byte_idx] & (1 << bit_idx)):
                    missing = piece.get_missing_blocks()
                    for offset in missing:
                        piece.requested_blocks.add(offset)
                        length = min(BLOCK_SIZE, piece.length - offset)
                        await peer.send_request(piece.index, offset, length)
                        if not hasattr(peer, 'my_requests'):
                            peer.my_requests = set()
                        peer.my_requests.add((piece, offset))
                        if peer.pending_requests >= 250:
                            peer.last_piece_scan_idx = start_idx
                            return
            
            start_idx = (start_idx + 1) % total_pieces
            
        peer.last_piece_scan_idx = start_idx

    def add_peer(self, peer: PeerConnection):
        if peer.ip not in self.seen_ips:
            self.seen_ips.add(peer.ip)
            self.pending_peers.append(peer)

    async def _peer_worker(self, peer: PeerConnection):
        if not await peer.connect():
            return
            
        if not await peer.handshake():
            peer.disconnect()
            return
            
        # Extension handshake
        if peer.supports_extensions:
            await peer.send_extended_handshake(1, 2) # map ut_metadata to 1, ut_pex to 2
            
        self.active_peers.append(peer)
        
        while self.is_running and peer.connected:
            try:
                msg_id, payload = await asyncio.wait_for(peer.receive_message(), timeout=5.0)
                
                if msg_id == -1:
                    continue # Keep-alive
                    
                if msg_id == MSG_EXTENDED:
                    if len(payload) >= 2 and payload[0] == 0: # Extended Handshake
                        peer.parse_extended_handshake(payload)
                        
                        # Request metadata piece 0 if fetching
                        if self.fetching_metadata and peer.peer_ut_metadata_id is not None and peer.metadata_size > 0:
                            if self.metadata_size == 0:
                                self.metadata_size = peer.metadata_size
                                
                            if 0 not in self.metadata_buffer and 0 not in self.metadata_requested:
                                self.metadata_requested.add(0)
                                if not hasattr(peer, 'metadata_requests'):
                                    peer.metadata_requests = set()
                                peer.metadata_requests.add(0)
                                await peer.send_metadata_request(0)
                                
                    elif len(payload) >= 2 and payload[0] == 1: # ut_metadata ID (assuming we mapped it to 1, but we should use peer's ut_metadata if sending, and our 1 for receiving. Wait, if msg extended ID is 1, it means peer sent us a ut_metadata message)
                        msg_type, piece_index, raw_data = peer.parse_metadata_message(payload[1:])
                        if msg_type == 1 and piece_index is not None and raw_data is not None:
                            if hasattr(peer, 'metadata_requests'):
                                peer.metadata_requests.discard(piece_index)
                            self._handle_metadata_piece(piece_index, raw_data)
                            
                            # Request next piece
                            if self.fetching_metadata and peer.peer_ut_metadata_id is not None and peer.metadata_size > 0:
                                num_pieces = (peer.metadata_size + BLOCK_SIZE - 1) // BLOCK_SIZE
                                for i in range(num_pieces):
                                    if i not in self.metadata_buffer and i not in self.metadata_requested:
                                        self.metadata_requested.add(i)
                                        if not hasattr(peer, 'metadata_requests'):
                                            peer.metadata_requests = set()
                                        peer.metadata_requests.add(i)
                                        await peer.send_metadata_request(i)
                                        break
                                        
                    elif len(payload) >= 2 and payload[0] == 2: # ut_pex
                        added_peers, dropped_peers = peer.parse_pex_message(payload[1:])
                        for ip, port in added_peers:
                            if ip not in self.seen_ips:
                                from engine.peer_protocol import PeerConnection
                                new_peer = PeerConnection(ip, port, peer.info_hash, peer.my_peer_id)
                                self.add_peer(new_peer)
                                        
                elif msg_id == MSG_CHOKE:
                    peer.peer_choking = True
                elif msg_id == MSG_UNCHOKE:
                    peer.peer_choking = False
                elif msg_id == MSG_BITFIELD:
                    peer.bitfield = bytearray(payload)
                elif msg_id == MSG_HAVE:
                    if len(payload) >= 4:
                        piece_idx = struct.unpack(">I", payload)[0]
                        byte_idx = piece_idx // 8
                        bit_idx = 7 - (piece_idx % 8)
                        if len(peer.bitfield) <= byte_idx:
                            peer.bitfield.extend(b"\x00" * (byte_idx - len(peer.bitfield) + 1))
                        peer.bitfield[byte_idx] |= (1 << bit_idx)
                elif msg_id == MSG_PIECE:
                    if len(payload) >= 8:
                        index, begin = struct.unpack(">II", payload[:8])
                        block_data = payload[8:]
                        if peer.pending_requests > 0:
                            peer.pending_requests -= 1
                        if hasattr(peer, 'my_requests'):
                            peer.my_requests.discard((self.pieces[index], begin))
                        peer.bytes_downloaded += len(block_data)
                        await self._handle_piece_block(index, begin, block_data)
                        
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                # print(f"Peer worker error: {e}")
                pass
                peer.disconnect()
                break
                
            if not self.fetching_metadata and not peer.peer_choking:
                await self._request_blocks(peer)
                
        if peer in self.active_peers:
            self.active_peers.remove(peer)
            
        if hasattr(peer, 'my_requests'):
            for piece, offset in peer.my_requests:
                if offset in piece.requested_blocks:
                    piece.requested_blocks.remove(offset)
                piece.fully_requested = False
            peer.my_requests.clear()
            
        if hasattr(peer, 'metadata_requests'):
            for i in peer.metadata_requests:
                self.metadata_requested.discard(i)
            peer.metadata_requests.clear()

    async def _broadcast_pex(self):
        compact_peers = bytearray()
        count = 0
        for p in self.active_peers:
            if p.connected:
                parts = p.ip.split('.')
                if len(parts) == 4:
                    try:
                        compact_peers.extend(struct.pack(">BBBBH", int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]), p.port))
                        count += 1
                        if count >= 50:
                            break
                    except:
                        pass
        
        if len(compact_peers) > 0:
            for p in self.active_peers:
                if p.connected and getattr(p, 'peer_ut_pex_id', None) is not None:
                    asyncio.create_task(p.send_pex_message(bytes(compact_peers), b""))

    def _update_choking(self):
        import random
        interested_peers = [p for p in self.active_peers if getattr(p, 'peer_interested', False) and p.connected]
        interested_peers.sort(key=lambda p: getattr(p, 'bytes_downloaded', 0), reverse=True)
        
        for p in self.active_peers:
            p.bytes_downloaded = 0
            
        unchoke_slots = 15
        for i, p in enumerate(interested_peers):
            if i < unchoke_slots:
                if getattr(p, 'am_choking', True):
                    p.am_choking = False
                    asyncio.create_task(p.send_message(MSG_UNCHOKE))
            else:
                if not getattr(p, 'am_choking', True):
                    p.am_choking = True
                    asyncio.create_task(p.send_message(MSG_CHOKE))
                    
        rest = interested_peers[unchoke_slots:]
        if rest:
            opt_peer = random.choice(rest)
            if getattr(opt_peer, 'am_choking', True):
                opt_peer.am_choking = False
                asyncio.create_task(opt_peer.send_message(MSG_UNCHOKE))

    async def run(self):
        self.is_running = True
        last_speed_tick = asyncio.get_event_loop().time()
        last_pex_broadcast = asyncio.get_event_loop().time()
        last_choke_tick = asyncio.get_event_loop().time()
        last_shuffle_tick = asyncio.get_event_loop().time()
        
        while self.is_running:
            current_time = asyncio.get_event_loop().time()
            if current_time - last_speed_tick >= 1.0:
                self.down_speed = self.bytes_downloaded_window
                self.up_speed = self.bytes_uploaded_window
                self.bytes_downloaded_window = 0
                self.bytes_uploaded_window = 0
                last_speed_tick = current_time
                
            if current_time - last_shuffle_tick >= 5.0:
                if not self.sequential_mode and len(self.incomplete_pieces) > 0:
                    import random
                    random.shuffle(self.incomplete_pieces)
                last_shuffle_tick = current_time
                
            if current_time - last_pex_broadcast >= 60.0:
                asyncio.create_task(self._broadcast_pex())
                last_pex_broadcast = current_time
                
            if current_time - last_choke_tick >= 10.0:
                self._update_choking()
                last_choke_tick = current_time
                
            if not self.fetching_metadata and self.torrent:
                if len(self.pieces) > 0 and len(self.completed_pieces) == len(self.pieces):
                    self.is_running = False
                    break
            
            # Start workers for pending peers
            for peer in list(self.pending_peers):
                self.pending_peers.remove(peer)
                asyncio.create_task(self._peer_worker(peer))
                
            # If standard downloading mode, ensure we broadcast interest
            if not self.fetching_metadata and self.torrent:
                for peer in self.active_peers:
                    if not peer.am_interested:
                        peer.am_interested = True
                        asyncio.create_task(peer.send_message(MSG_INTERESTED))
            
            await asyncio.sleep(1)
