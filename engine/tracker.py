import urllib.parse
import urllib.request
import asyncio
import struct
import random
import socket
from typing import List, Tuple
from engine.bencoding import bdecode
from engine.logger import log

def generate_peer_id(client_prefix: bytes = b"-AG0001-") -> bytes:
    """Generates a 20-byte peer_id"""
    suffix = bytes(random.randint(0, 255) for _ in range(20 - len(client_prefix)))
    return client_prefix + suffix

class TrackerClient:
    def __init__(self, announce_url: str, info_hash: bytes, peer_id: bytes):
        self.announce_url = announce_url
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.port = 6881

    async def announce(self, uploaded: int = 0, downloaded: int = 0, left: int = 0, event: str = "started") -> List[Tuple[str, int]]:
        """
        Announces to the tracker and returns a list of (ip, port) for peers.
        """
        log(f"[Tracker] Announcing to {self.announce_url} (left={left}, event={event})")
        loop = asyncio.get_running_loop()
        try:
            if self.announce_url.startswith('udp://'):
                return await loop.run_in_executor(None, self._make_udp_request, uploaded, downloaded, left, event)
            else:
                params = {
                    'info_hash': self.info_hash,
                    'peer_id': self.peer_id,
                    'port': self.port,
                    'uploaded': uploaded,
                    'downloaded': downloaded,
                    'left': left,
                    'compact': 1,
                    'event': event
                }
                query_string = urllib.parse.urlencode(params)
                url = f"{self.announce_url}?{query_string}"
                response_data = await loop.run_in_executor(None, self._make_http_request, url)
                peers = self._parse_http_response(response_data)
                log(f"[Tracker] Received {len(peers)} peers from {self.announce_url}")
                return peers
        except Exception as e:
            log(f"Tracker request failed ({self.announce_url}): {e}")
            return []

    def _make_http_request(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={'User-Agent': 'Antigravity-BT/0.0.1'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read()
            
    def _parse_http_response(self, response_data: bytes) -> List[Tuple[str, int]]:
        try:
            decoded, _, _ = bdecode(response_data)
        except Exception as e:
            print(f"Failed to bdecode tracker response: {e}")
            return []
            
        if not isinstance(decoded, dict):
            print("Invalid tracker response")
            return []
            
        if b'failure reason' in decoded:
            print(f"Tracker failure: {decoded[b'failure reason'].decode('utf-8', errors='ignore')}")
            return []
            
        peers = decoded.get(b'peers')
        if not peers:
            return []
            
        peer_list = []
        if isinstance(peers, bytes):
            # Compact format: 6 bytes per peer (4 bytes IP, 2 bytes port)
            for i in range(0, len(peers), 6):
                if i + 6 > len(peers):
                    break
                ip_bytes = peers[i:i+4]
                port_bytes = peers[i+4:i+6]
                
                ip = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
                port = struct.unpack(">H", port_bytes)[0]
                peer_list.append((ip, port))
        elif isinstance(peers, list):
            # Dictionary format
            for p in peers:
                if isinstance(p, dict) and b'ip' in p and b'port' in p:
                    ip = p[b'ip'].decode('utf-8', errors='ignore')
                    port = p[b'port']
                    peer_list.append((ip, port))
                    
        return peer_list

    def _make_udp_request(self, uploaded: int, downloaded: int, left: int, event: str) -> List[Tuple[str, int]]:
        parsed = urllib.parse.urlparse(self.announce_url)
        host = parsed.hostname
        port = parsed.port or 80
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)
        
        try:
            # 1. Connect Request
            transaction_id = random.randint(0, 0xFFFFFFFF)
            # 64-bit magic, 32-bit action (0), 32-bit transaction_id
            connect_req = struct.pack(">QII", 0x41727101980, 0, transaction_id)
            sock.sendto(connect_req, (host, port))
            
            connect_resp, _ = sock.recvfrom(2048)
            if len(connect_resp) < 16:
                return []
                
            action, res_transaction_id, connection_id = struct.unpack(">IIQ", connect_resp[:16])
            if action != 0 or res_transaction_id != transaction_id:
                return []
                
            # 2. Announce Request
            transaction_id = random.randint(0, 0xFFFFFFFF)
            event_map = {"none": 0, "completed": 1, "started": 2, "stopped": 3}
            event_id = event_map.get(event, 0)
            
            # 64-bit conn_id, 32-bit action (1), 32-bit trans_id, 20-byte info_hash, 20-byte peer_id
            # 64-bit down, 64-bit left, 64-bit up, 32-bit event, 32-bit IP, 32-bit key, 32-bit num_want, 16-bit port
            announce_req = struct.pack(">QII20s20sQQQIIIiH", 
                connection_id, 
                1, 
                transaction_id, 
                self.info_hash, 
                self.peer_id, 
                downloaded, 
                left, 
                uploaded, 
                event_id, 
                0, 
                random.randint(0, 0xFFFFFFFF), 
                -1, 
                self.port)
                
            sock.sendto(announce_req, (host, port))
            
            announce_resp, _ = sock.recvfrom(2048)
            if len(announce_resp) < 20:
                return []
                
            action, res_transaction_id, interval, leechers, seeders = struct.unpack(">IIIII", announce_resp[:20])
            if action != 1 or res_transaction_id != transaction_id:
                return []
                
            peer_list = []
            peers_data = announce_resp[20:]
            for i in range(0, len(peers_data), 6):
                if i + 6 > len(peers_data):
                    break
                ip_bytes = peers_data[i:i+4]
                port_bytes = peers_data[i+4:i+6]
                ip = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
                peer_port = struct.unpack(">H", port_bytes)[0]
                peer_list.append((ip, peer_port))
                
            log(f"[Tracker] Received {len(peer_list)} peers from {self.announce_url}")
            return peer_list
        except Exception as e:
            log(f"UDP Tracker request failed ({self.announce_url}): {e}")
            return []
        finally:
            sock.close()
