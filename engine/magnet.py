import urllib.parse
import base64
import binascii

class MagnetLink:
    def __init__(self, uri: str):
        self.uri = uri
        self.info_hash: bytes = b""
        self.trackers: list[str] = []
        self.name: str = ""
        self._parse()

    def _parse(self):
        if not self.uri.startswith("magnet:?"):
            raise ValueError("Invalid magnet link format")

        query = self.uri[8:]
        params = urllib.parse.parse_qs(query)

        # Extract info_hash from xt
        xt_list = params.get('xt', [])
        if not xt_list:
            raise ValueError("Magnet link missing 'xt' parameter")

        for xt in xt_list:
            if xt.startswith("urn:btih:"):
                hash_str = xt[9:]
                if len(hash_str) == 40:
                    # Hex format
                    try:
                        self.info_hash = bytes.fromhex(hash_str)
                    except ValueError:
                        raise ValueError("Invalid hex in urn:btih")
                elif len(hash_str) == 32:
                    # Base32 format
                    try:
                        # Base32 needs padding if not padded
                        padding = '=' * (8 - len(hash_str) % 8) if len(hash_str) % 8 != 0 else ''
                        self.info_hash = base64.b32decode(hash_str + padding, casefold=True)
                    except binascii.Error:
                        raise ValueError("Invalid base32 in urn:btih")
                else:
                    raise ValueError(f"Invalid urn:btih length: {len(hash_str)}")
                break
                
        if not self.info_hash:
            raise ValueError("No valid btih found in magnet link")

        # Extract trackers
        self.trackers = params.get('tr', [])
        
        # Extract name
        dn_list = params.get('dn', [])
        if dn_list:
            self.name = dn_list[0]
        else:
            self.name = self.info_hash.hex()
