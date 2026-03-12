# SecureLink — Protocol API Documentation
**Member C Deliverable | Data Engineer**

This document explains how to use `src/protocol.py` in your code.  
No need to understand the internals — just call the functions below.

---

## Setup

```python
import sys, os
sys.path.insert(0, 'src')   # or adjust path as needed
from protocol import *
```

Install the one dependency:
```bash
pip install cryptography
```

---

## 1. Packets

Every message sent over the network must be wrapped in a packet.

### `build_packet(msg_type, payload, flags, message_id, encrypt_payload, key)`

Builds a binary packet ready to send over a socket.

```python
from protocol import build_packet, parse_packet, MSG_CHAT

packet = build_packet(
    msg_type=MSG_CHAT,
    payload=b"Hello Bob!",
    flags=0,
    message_id="msg-001",
    encrypt_payload=False,
    key=None
)

sock.sendall(packet)
```

### `parse_packet(raw_bytes)`

Reads a raw binary packet and returns a dictionary.

```python
data = parse_packet(raw_bytes)

print(data['payload'])        # the message content (bytes)
print(data['msg_type'])       # type of message
print(data['checksum_valid']) # True if packet is not corrupted
print(data['encrypted'])      # True if payload is encrypted
```

### `recv_packet(sock)`

Receives a complete packet from a socket. **Use this instead of `sock.recv()` directly.**

```python
from protocol import recv_packet

data = recv_packet(sock)   # blocks until a full packet arrives
print(data['payload'])
```

### Message Types (use these constants)

| Constant | Value | Use for |
|---|---|---|
| `MSG_CHAT` | 0x01 | Normal chat messages |
| `MSG_FILE` | 0x02 | File transfer |
| `MSG_ACK` | 0x03 | Acknowledgement |
| `MSG_ERROR` | 0x04 | Error reporting |
| `MSG_HANDSHAKE` | 0x05 | Connection setup |

---

## 2. Encryption

### `generate_key(path)`

Generates a new AES-256 encryption key and saves it to a file.  
**Call this once** — then share the key file with your teammate.

```python
from protocol import generate_key

key = generate_key('securelink.key')  # saves key to file
```

### `load_key(path)`

Loads an existing key from a file.

```python
from protocol import load_key

key = load_key('securelink.key')
```

### `encrypt(data, key)` / `decrypt(data, key)`

Encrypt or decrypt raw bytes.

```python
from protocol import encrypt, decrypt, generate_key

key = generate_key('securelink.key')

encrypted = encrypt(b"Secret message", key)
original  = decrypt(encrypted, key)

print(original)  # b"Secret message"
```

### Sending an encrypted chat message (full example)

```python
key = load_key('securelink.key')

packet = build_packet(
    msg_type=MSG_CHAT,
    payload=b"Hello Bob!",
    flags=0,
    message_id="msg-001",
    encrypt_payload=True,   # ← this encrypts automatically
    key=key
)

sock.sendall(packet)
```

---

## 3. File Transfer

### `send_file(sock, filepath, key, encrypt_data)`

Sends a file over a connected socket in 4KB chunks with encryption.

```python
from protocol import send_file, load_key

key = load_key('securelink.key')
send_file(sock, 'photos/image.jpg', key, encrypt_data=True)
```

### `receive_file(sock, save_dir, key)`

Receives a file and saves it to a folder. Returns the saved file path.

```python
from protocol import receive_file, load_key

key = load_key('securelink.key')
saved_path = receive_file(sock, 'downloads/', key)

print(f"File saved to: {saved_path}")
```

---

## 4. Database — for Member A (UI)

These functions save and load chat messages from SQLite.

### `init_db(db_path)`

Creates the database. **Call this once when your app starts.**

```python
from protocol import init_db

init_db(db_path='securelink.db')
```

### `save_message(sender, content, message_id, timestamp, receiver, db_path)`

Saves a message to the database.

```python
from protocol import save_message
import time

save_message(
    sender='Alice',
    content='Hey Bob!',
    message_id='msg-001',
    timestamp=int(time.time() * 1000),  # milliseconds
    receiver='Bob',
    db_path='securelink.db'
)
```

### `load_history(db_path, limit)`

Loads all saved messages, newest last.

```python
from protocol import load_history

messages = load_history(db_path='securelink.db', limit=50)

for msg in messages:
    print(f"{msg['sender']}: {msg['content']}")
```

### `delete_message(message_id, db_path)`

Deletes a message by its ID (for self-destruct feature).

```python
from protocol import delete_message

delete_message('msg-001', db_path='securelink.db')
```

---

## Quick Reference for Member B (Network Engineer)

| You need to... | Call this |
|---|---|
| Receive a packet safely | `recv_packet(sock)` |
| Send an encrypted message | `build_packet(..., encrypt_payload=True, key=key)` |
| Check if packet is corrupted | `data['checksum_valid']` |
| Send a file | `send_file(sock, path, key, encrypt_data=True)` |
| Receive a file | `receive_file(sock, save_dir, key)` |

## Quick Reference for Member A (UI / Ashish)

| You need to... | Call this |
|---|---|
| Start the app | `init_db('securelink.db')` |
| Save a received message | `save_message(...)` |
| Load chat history | `load_history('securelink.db')` |
| Delete a message | `delete_message(msg_id, 'securelink.db')` |

---

*All functions are in `src/protocol.py`. Run `python3 src/protocol.py` to verify everything works (41 tests, all passing).*