import os
import time
import ctypes
from ctypes import wintypes

def create_sparse_file(path, size_mb=90000):
    start = time.time()
    with open(path, 'wb') as f:
        pass
        
    # Mark as sparse
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    FSCTL_SET_SPARSE = 590020
    
    handle = ctypes.windll.kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        0,
        None,
        OPEN_EXISTING,
        0x80,
        None
    )
    
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
    
    # Now try to truncate to 90GB
    with open(path, 'r+b') as f:
        f.truncate(size_mb * 1024 * 1024)
        
    end = time.time()
    print(f"Created sparse file and truncated to 90GB in {end - start:.4f} seconds.")

if __name__ == "__main__":
    create_sparse_file("test_sparse_truncate.dat")
