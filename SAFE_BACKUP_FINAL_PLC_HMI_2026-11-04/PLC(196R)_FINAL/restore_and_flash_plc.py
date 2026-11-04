import os
import sys
import struct
import socket
import time

sys.stdout.reconfigure(encoding='utf-8')

cdir = os.path.dirname(os.path.abspath(__file__))
bin_path = os.path.join(cdir, "ladder_patched.bin")
with open(bin_path, "rb") as f:
    data = f.read()

def stm32_crc32(b):
    crc = 0xFFFFFFFF
    for i in range(0, len(b), 4):
        w = struct.unpack('<I', b[i:i+4])[0]
        crc ^= w
        for _ in range(32):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc

crc = stm32_crc32(data)
print(f"Flashing ladder_patched.bin to PLC 192.168.1.240: len={len(data)}, crc={crc}")

s23 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s23.settimeout(5.0)
s23.connect(('192.168.1.240', 23))
time.sleep(0.2)
try:
    s23.recv(1024)
except Exception:
    pass

def cmd23(c, wait=0.35):
    s23.sendall((c + '\r\n').encode())
    time.sleep(wait)
    try:
        return s23.recv(4096).decode(errors='ignore')
    except Exception as e:
        return str(e)

print("Auth:", repr(cmd23("283320")))
print("Chks before:", repr(cmd23("chks", 0.3)))
print("Stop:", repr(cmd23("stop")))
prog_cmd = f"program enable {len(data)} {crc} 7626"
print("ProgEnable:", repr(cmd23(prog_cmd, 0.4)))

s61 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s61.settimeout(5.0)
s61.connect(('192.168.1.240', 61163))
banner61 = s61.recv(1024).decode(errors='ignore')
print("s61 banner:", repr(banner61))

offset = 0
chunk_idx = 0
while offset < len(data):
    chunk = data[offset:offset+512]
    s61.sendall(chunk)
    offset += len(chunk)
    chunk_idx += 1
    if offset < len(data):
        ack = s61.recv(1024).decode(errors='ignore')
        if 'acked' not in ack:
            print(f"Unexpected ack at chunk {chunk_idx}: {ack!r}")
            break

time.sleep(0.8)
try:
    print("s61 final:", repr(s61.recv(1024).decode(errors='ignore')))
except Exception as e:
    print("s61 final err:", e)
s61.close()

print("Run:", repr(cmd23("run", 0.8)))
print("Chks after:", repr(cmd23("chks", 0.4)))
print("Info after:", repr(cmd23("info", 0.4)))
s23.close()
