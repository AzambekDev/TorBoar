class BencodeDecodeError(Exception):
    pass

class BencodeDecoder:
    def __init__(self, data: bytes):
        self.data = data
        self.index = 0
        self.info_raw = None # To store the raw bytes of the 'info' dict

    def decode(self):
        return self._decode_next()

    def _decode_next(self):
        if self.index >= len(self.data):
            raise BencodeDecodeError("Unexpected end of data")
        
        char = self.data[self.index:self.index+1]
        if char == b'i':
            return self._decode_int()
        elif char == b'l':
            return self._decode_list()
        elif char == b'd':
            return self._decode_dict()
        elif char in b'0123456789':
            return self._decode_string()
        else:
            raise BencodeDecodeError(f"Invalid character at {self.index}: {char}")

    def _decode_int(self):
        self.index += 1 # skip 'i'
        end = self.data.find(b'e', self.index)
        if end == -1:
            raise BencodeDecodeError("Unterminated integer")
        val = int(self.data[self.index:end])
        self.index = end + 1
        return val

    def _decode_string(self):
        colon = self.data.find(b':', self.index)
        if colon == -1:
            raise BencodeDecodeError("Unterminated string length")
        length = int(self.data[self.index:colon])
        start = colon + 1
        end = start + length
        if end > len(self.data):
            raise BencodeDecodeError("String length exceeds data")
        val = self.data[start:end]
        self.index = end
        return val

    def _decode_list(self):
        self.index += 1 # skip 'l'
        lst = []
        while self.index < len(self.data) and self.data[self.index:self.index+1] != b'e':
            lst.append(self._decode_next())
        if self.index >= len(self.data) or self.data[self.index:self.index+1] != b'e':
            raise BencodeDecodeError("Unterminated list")
        self.index += 1 # skip 'e'
        return lst

    def _decode_dict(self):
        self.index += 1 # skip 'd'
        d = {}
        while self.index < len(self.data) and self.data[self.index:self.index+1] != b'e':
            key = self._decode_string()
            
            # If the key is 'info', we want to capture the exact bytes of the value
            capture_raw = (key == b'info')
            start_idx = self.index if capture_raw else 0
            
            val = self._decode_next()
            
            if capture_raw:
                self.info_raw = self.data[start_idx:self.index]
                
            d[key] = val
            
        if self.index >= len(self.data) or self.data[self.index:self.index+1] != b'e':
            raise BencodeDecodeError("Unterminated dictionary")
        self.index += 1 # skip 'e'
        return d

def bdecode(data: bytes):
    """
    Decodes bencoded data and returns a tuple of (decoded_object, info_raw_bytes, consumed_length).
    info_raw_bytes will be None if the dictionary doesn't contain an 'info' key.
    """
    decoder = BencodeDecoder(data)
    result = decoder.decode()
    return result, decoder.info_raw, decoder.index

def bencode(obj) -> bytes:
    if isinstance(obj, int):
        return b'i' + str(obj).encode('ascii') + b'e'
    elif isinstance(obj, bytes):
        return str(len(obj)).encode('ascii') + b':' + obj
    elif isinstance(obj, str):
        b = obj.encode('utf-8')
        return str(len(b)).encode('ascii') + b':' + b
    elif isinstance(obj, list):
        return b'l' + b''.join(bencode(x) for x in obj) + b'e'
    elif isinstance(obj, dict):
        # Keys must be strings/bytes and sorted
        encoded_items = []
        for k, v in obj.items():
            if isinstance(k, str):
                k = k.encode('utf-8')
            if not isinstance(k, bytes):
                raise TypeError(f"Dictionary keys must be strings or bytes, got {type(k)}")
            encoded_items.append((k, bencode(v)))
        
        # Sort by raw bytes of the key
        encoded_items.sort(key=lambda x: x[0])
        
        parts = [b'd']
        for k, v in encoded_items:
            parts.append(bencode(k))
            parts.append(v)
        parts.append(b'e')
        return b''.join(parts)
    else:
        raise TypeError(f"Unsupported type for bencoding: {type(obj)}")
