import hashlib
from typing import List, Dict, Any, Optional
import os
from engine.bencoding import bdecode, bencode

class TorrentFile:
    def __init__(self, file_path: Optional[str] = None, info_raw: Optional[bytes] = None):
        self.file_path = file_path
        self.announce: str = ""
        self.info_hash: bytes = b""
        self.piece_length: int = 0
        self.pieces: bytes = b""
        self.name: str = ""
        self.total_size: int = 0
        self.files: List[Dict[str, Any]] = [] # [{'length': int, 'path': str}]
        
        if file_path:
            self._parse_file()
        elif info_raw:
            self._parse_info(info_raw)

    def _parse_file(self):
        with open(self.file_path, 'rb') as f:
            data = f.read()
        
        decoded, info_raw, _ = bdecode(data)
        if not isinstance(decoded, dict) or b'info' not in decoded:
            raise ValueError("Invalid torrent file: missing 'info' dictionary")
        
        # Announce URL
        self.announce = decoded.get(b'announce', b'').decode('utf-8')
        
        # Info dictionary
        self._parse_info(info_raw, decoded[b'info'])

    def _parse_info(self, info_raw: bytes, info_dict: Optional[Dict] = None):
        if info_dict is None:
            decoded, _, _ = bdecode(info_raw)
            if not isinstance(decoded, dict):
                raise ValueError("Invalid info bytes")
            info = decoded
        else:
            info = info_dict
        
        # Name
        self.name = info.get(b'name', b'').decode('utf-8')
        
        # Piece length and pieces
        self.piece_length = info.get(b'piece length', 0)
        self.pieces = info.get(b'pieces', b'')
        
        # Files and size
        if b'length' in info:
            # Single file mode
            self.total_size = info[b'length']
            self.files = [{'length': self.total_size, 'path': self.name}]
        elif b'files' in info:
            # Multi file mode
            self.total_size = 0
            for f_dict in info[b'files']:
                length = f_dict[b'length']
                self.total_size += length
                path_parts = [p.decode('utf-8') for p in f_dict[b'path']]
                self.files.append({
                    'length': length,
                    'path': os.path.join(self.name, *path_parts)
                })
        else:
            raise ValueError("Invalid torrent file: missing 'length' and 'files'")

        # Calculate info_hash using the raw info dictionary bytes
        if info_raw is None:
            # Fallback if the parser didn't capture it (shouldn't happen with our parser)
            info_raw = bencode(info)
            
        sha1 = hashlib.sha1()
        sha1.update(info_raw)
        self.info_hash = sha1.digest()
