import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from protocol import receive_file, generate_key, load_key
import socket

KEY_PATH = 'securelink.key'
PORT = 9999

if os.path.exists(KEY_PATH):
    key = load_key(KEY_PATH)
    print(f"[Receiver] Loaded existing key")
else:
    key = generate_key(KEY_PATH)
    print(f"[Receiver] Generated new key")

OUTPUT_DIR = 'assets'
print(f"[Receiver] Listening on port {PORT}...")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('127.0.0.1', PORT))
server.listen(1)

conn, addr = server.accept()
print(f"[Receiver] Connected from {addr}")

saved_path = receive_file(conn, OUTPUT_DIR, key)

conn.close()
server.close()

print(f"\n[Receiver] ✓ File saved!")