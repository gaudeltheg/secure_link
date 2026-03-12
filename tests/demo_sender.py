import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from protocol import send_file, generate_key, load_key
import socket, time

KEY_PATH = 'securelink.key'
PORT = 9999
FILE_TO_SEND = 'assets/secret.txt'

if os.path.exists(KEY_PATH):
    key = load_key(KEY_PATH)
    print(f"[Sender] Loaded existing key")
else:
    key = generate_key(KEY_PATH)
    print(f"[Sender] Generated new key")

print(f"[Sender] Connecting to port {PORT}...")
time.sleep(1)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('127.0.0.1', PORT))

send_file(sock, FILE_TO_SEND, key, encrypt_data=True)

sock.close()
print("[Sender] ✓ File sent with encryption!")