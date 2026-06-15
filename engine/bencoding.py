class BencodeDecodeError(Exception):
    pass

class BencodeDecoder:
    def __init__(self, data: bytes):
        self.data = data
        self.index = 0
        self.info_raw = None

    def decode(self):
        return self._decode_next(0)

    def _decode_next(self, depth: int):
        if depth > 50:
            raise BencodeDecodeError("Max recursion depth exceeded")
        if self.index >= len(self.data):
            raise BencodeDecodeError("Unexpected end of data")
        
        char = self.data[self.index]
        if char == 105: # b'i'
            return self._decode_int()
        elif char == 108: # b'l'
            return self._decode_list(depth + 1)
        elif char == 100: # b'd'
            return self._decode_dict(depth + 1)
        elif 48 <= char <= 57: # '0'-'9'
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

    def _decode_list(self, depth: int):
        self.index += 1 # skip 'l'
        lst = []
        while self.index < len(self.data) and self.data[self.index] != 101: # b'e'
            lst.append(self._decode_next(depth))
        if self.index >= len(self.data) or self.data[self.index] != 101:
            raise BencodeDecodeError("Unterminated list")
        self.index += 1 # skip 'e'
        return lst

    def _decode_dict(self, depth: int):
        self.index += 1 # skip 'd'
        d = {}
        while self.index < len(self.data) and self.data[self.index] != 101: # b'e'
            key = self._decode_string()
            
            capture_raw = (key == b'info')
            start_idx = self.index if capture_raw else 0
            
            val = self._decode_next(depth)
            
            if capture_raw:
                self.info_raw = self.data[start_idx:self.index]
                
            d[key] = val
            
        if self.index >= len(self.data) or self.data[self.index] != 101:
            raise BencodeDecodeError("Unterminated dictionary")
        self.index += 1 # skip 'e'
        return d

def _bencode_to_buffer(obj, buffer: bytearray):
    if isinstance(obj, int):
        buffer.extend(b'i')
        buffer.extend(str(obj).encode('ascii'))
        buffer.extend(b'e')
    elif isinstance(obj, bytes):
        buffer.extend(str(len(obj)).encode('ascii'))
        buffer.extend(b':')
        buffer.extend(obj)
    elif isinstance(obj, str):
        b = obj.encode('utf-8')
        buffer.extend(str(len(b)).encode('ascii'))
        buffer.extend(b':')
        buffer.extend(b)
    elif isinstance(obj, list):
        buffer.extend(b'l')
        for item in obj:
            _bencode_to_buffer(item, buffer)
        buffer.extend(b'e')
    elif isinstance(obj, dict):
        buffer.extend(b'd')
        # Keys must be strings/bytes and sorted
        items = []
        for k, v in obj.items():
            if isinstance(k, str):
                k = k.encode('utf-8')
            if not isinstance(k, bytes):
                raise TypeError(f"Dictionary keys must be strings or bytes, got {type(k)}")
            items.append((k, v))
        
        items.sort(key=lambda x: x[0])
        for k, v in items:
            _bencode_to_buffer(k, buffer)
            _bencode_to_buffer(v, buffer)
        buffer.extend(b'e')
    else:
        raise TypeError(f"Unsupported type for bencoding: {type(obj)}")

def bencode(obj) -> bytes:
    buffer = bytearray()
    _bencode_to_buffer(obj, buffer)
    return bytes(buffer)

def bdecode(data: bytes):
    """
    Decodes bencoded data and returns a tuple of (decoded_object, info_raw_bytes, consumed_length).
    info_raw_bytes will be None if the dictionary doesn't contain an 'info' key.
    """
    decoder = BencodeDecoder(data)
    result = decoder.decode()
    return result, decoder.info_raw, decoder.index
