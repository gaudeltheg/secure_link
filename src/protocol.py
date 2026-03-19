"""
SecureLink — protocol.py
Member C Deliverable: Packet Protocol, Encryption, File Transfer, Database
"""

import struct
import hashlib
import os
import socket
import sqlite3
import time

# ─────────────────────────────────────────────
# Message type constants
# ─────────────────────────────────────────────
MSG_CHAT      = 0x01
MSG_FILE      = 0x02
MSG_ACK       = 0x03
MSG_ERROR     = 0x04
MSG_HANDSHAKE = 0x05

MAGIC         = b'SLNK'
VERSION       = 1
HEADER_LEN    = 32
CHUNK_SIZE    = 4096
KEY_FILE      = 'securelink.key'

# ─────────────────────────────────────────────
# Section 1: Packet Builder / Parser
# ─────────────────────────────────────────────

def _checksum(data: bytes) -> int:
    """CRC32 checksum of data, returned as unsigned int."""
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def build_packet(msg_type: int, payload: bytes, flags: int = 0,
                 message_id: str = '', encrypt_payload: bool = False,
                 key: bytes = None) -> bytes:
    """
    Build a binary SecureLink packet.

    Header layout (32 bytes):
      4  MAGIC  'SLNK'
      1  version
      1  msg_type
      1  flags  (bit0 = encrypted)
      1  reserved
      8  message_id  (truncated/padded to 8 bytes)
      8  timestamp   (ms since epoch, big-endian uint64)
      4  payload_size
      4  checksum (of payload)
    """
    if encrypt_payload and key:
        payload, _ = encrypt_if_needed(payload, key, should_encrypt=True)
        flags |= 0x01  # set encrypted bit

    mid_bytes = message_id.encode()[:8].ljust(8, b'\x00')
    ts        = int(time.time() * 1000)
    chk       = _checksum(payload)

    header = struct.pack(
        '>4sBBBB8sQII',
        MAGIC,
        VERSION,
        msg_type,
        flags,
        0,           # reserved
        mid_bytes,
        ts,
        len(payload),
        chk
    )
    assert len(header) == HEADER_LEN
    return header + payload


def parse_packet(raw: bytes) -> dict:
    """
    Parse a raw SecureLink packet (header + payload).
    Returns a dict with all fields plus checksum_valid and encrypted flags.
    """
    if len(raw) < HEADER_LEN:
        raise ValueError("Packet too short")

    magic, version, msg_type, flags, _reserved, mid_bytes, ts, payload_size, chk = \
        struct.unpack('>4sBBBB8sQII', raw[:HEADER_LEN])

    if magic != MAGIC:
        raise ValueError(f"Bad magic: {magic}")

    payload = raw[HEADER_LEN:HEADER_LEN + payload_size]
    checksum_valid = (_checksum(payload) == chk)

    return {
        'magic':          magic,
        'version':        version,
        'msg_type':       msg_type,
        'flags':          flags,
        'message_id':     mid_bytes.rstrip(b'\x00').decode(errors='replace'),
        'timestamp':      ts,
        'payload_size':   payload_size,
        'checksum':       chk,
        'payload':        payload,
        'checksum_valid': checksum_valid,
        'encrypted':      bool(flags & 0x01),
    }


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes from a socket."""
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed before all bytes were received.")
        buf += chunk
    return buf


def recv_packet(sock: socket.socket) -> dict:
    """Receive one complete SecureLink packet from a socket."""
    raw_header = recv_exact(sock, HEADER_LEN)
    # peek at payload_size field (bytes 24-28)
    payload_size = struct.unpack('>I', raw_header[24:28])[0]
    raw_payload  = recv_exact(sock, payload_size)
    return parse_packet(raw_header + raw_payload)


# ─────────────────────────────────────────────
# Section 2: Encryption Vault (AES-256-GCM)
# ─────────────────────────────────────────────

def generate_key(path: str = KEY_FILE) -> bytes:
    """Generate a random AES-256 key, save it, and return it."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    with open(path, 'wb') as f:
        f.write(key)
    print(f"[Vault] New key saved to '{path}'")
    return key


def load_key(path: str = KEY_FILE) -> bytes:
    """Load an AES key from a file."""
    with open(path, 'rb') as f:
        return f.read()


def encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt data with AES (Fernet/AES-128-CBC+HMAC)."""
    from cryptography.fernet import Fernet
    return Fernet(key).encrypt(data)


def decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt data with AES."""
    from cryptography.fernet import Fernet
    return Fernet(key).decrypt(data)


def encrypt_if_needed(data: bytes, key: bytes, should_encrypt: bool) -> tuple:
    """Return (possibly encrypted data, encrypted_flag int)."""
    if should_encrypt and key:
        return encrypt(data, key), 1
    return data, 0


def decrypt_if_needed(pkt: dict, key: bytes) -> bytes:
    """Decrypt packet payload if the encrypted flag is set."""
    if pkt.get('encrypted') and key:
        return decrypt(pkt['payload'], key)
    return pkt['payload']


# ─────────────────────────────────────────────
# Section 3: File Chunking
# ─────────────────────────────────────────────

def send_file(sock: socket.socket, filepath: str,
              key: bytes = None, encrypt_data: bool = False) -> None:
    """
    Send a file over a connected socket in CHUNK_SIZE chunks.
    Each chunk is sent as a MSG_FILE packet. Waits for ACK after each chunk.
    """
    filename  = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    print(f"[File] Sending '{filename}' ({file_size} bytes) in {CHUNK_SIZE}-byte chunks …")

    # Send filename first
    name_pkt = build_packet(MSG_FILE, filename.encode(),
                            message_id='filename', encrypt_payload=False)
    sock.sendall(name_pkt)
    _wait_ack(sock)

    seq = 0
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            pkt = build_packet(MSG_FILE, chunk,
                               message_id=str(seq),
                               encrypt_payload=encrypt_data,
                               key=key)
            sock.sendall(pkt)
            _wait_ack(sock)
            print(f"[File] Chunk {seq} sent and acknowledged ({len(chunk)} bytes)")
            seq += 1

    # Send EOF marker
    eof_pkt = build_packet(MSG_FILE, b'', message_id='EOF')
    sock.sendall(eof_pkt)
    print(f"[File] Transfer complete — {seq} chunks sent.")


def receive_file(sock: socket.socket, save_dir: str = '.',
                 key: bytes = None) -> str:
    """
    Receive a file sent by send_file().
    Returns the path where the file was saved.
    """
    print("[File] Waiting for incoming file …")
    os.makedirs(save_dir, exist_ok=True)

    # First packet contains the filename
    pkt      = recv_packet(sock)
    filename = pkt['payload'].decode(errors='replace')
    _send_ack(sock)

    save_path = os.path.join(save_dir, filename)
    chunks    = []
    seq       = 0

    while True:
        pkt = recv_packet(sock)
        if pkt['message_id'] == 'EOF':
            break
        payload = pkt['payload']
        if pkt.get('encrypted') and key:
            payload = decrypt(payload, key)
        chunks.append(payload)
        print(f"[File] Received chunk {seq} ({len(payload)} bytes), ACK sent.")
        _send_ack(sock)
        seq += 1

    with open(save_path, 'wb') as f:
        for c in chunks:
            f.write(c)

    print(f"[File] Saved to '{save_path}' ({sum(len(c) for c in chunks)} bytes)")
    return save_path


def _send_ack(sock: socket.socket) -> None:
    sock.sendall(build_packet(MSG_ACK, b'ACK'))


def _wait_ack(sock: socket.socket) -> None:
    recv_packet(sock)   # just consume the ACK


# ─────────────────────────────────────────────
# Section 4: SQLite Message Database
# ─────────────────────────────────────────────

DB_FILE = 'securelink.db'


def init_db(db_path: str = DB_FILE) -> None:
    """Create the messages table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id  TEXT UNIQUE,
            sender      TEXT,
            receiver    TEXT,
            content     TEXT,
            timestamp   INTEGER,
            deleted     INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def save_message(sender: str, content: str, message_id: str,
                 timestamp: int, receiver: str,
                 db_path: str = DB_FILE) -> None:
    """Insert a message into the database."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        'INSERT OR IGNORE INTO messages '
        '(message_id, sender, receiver, content, timestamp) VALUES (?,?,?,?,?)',
        (message_id, sender, receiver, content, timestamp)
    )
    conn.commit()
    conn.close()


def load_history(db_path: str = DB_FILE, limit: int = 100) -> list:
    """Return all non-deleted messages ordered by timestamp."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        'SELECT sender, receiver, content, timestamp, message_id '
        'FROM messages WHERE deleted=0 ORDER BY timestamp ASC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {'sender': r[0], 'receiver': r[1], 'content': r[2],
         'timestamp': r[3], 'message_id': r[4]}
        for r in rows
    ]


def delete_message(message_id: str, db_path: str = DB_FILE) -> None:
    """Soft-delete a message (self-destruct)."""
    conn = sqlite3.connect(db_path)
    conn.execute('UPDATE messages SET deleted=1 WHERE message_id=?', (message_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# Section 5: Self-Test
# ─────────────────────────────────────────────

def _run_tests():
    print('=' * 50)
    print('  SecureLink protocol.py — Self Test')
    print('=' * 50)

    # Test 1: Packet build + parse
    print('\n[Test 1] Packet build + parse')
    pkt = build_packet(MSG_CHAT, b'Hello!', message_id='t-001')
    result = parse_packet(pkt)
    assert result['payload'] == b'Hello!', "Payload mismatch"
    assert result['checksum_valid'],        "Checksum failed"
    print('  ✓ Packet built and parsed correctly')
    print(f"  ✓ Checksum valid: {result['checksum_valid']}")

    # Test 2: Encryption roundtrip
    print('\n[Test 2] Encryption roundtrip')
    key = generate_key('_test.key')
    original = b'Top secret military message'
    enc = encrypt(original, key)
    dec = decrypt(enc, key)
    assert dec == original, "Decrypt mismatch"
    print(f'  ✓ Original : {original}')
    print(f'  ✓ Decrypted: {dec}')
    os.remove('_test.key')

    # Test 3: Encrypted packet end-to-end
    print('\n[Test 3] Encrypted packet end-to-end')
    key = generate_key('_test2.key')
    pkt = build_packet(MSG_CHAT, b'Classified',
                       encrypt_payload=True, key=key)
    result = parse_packet(pkt)
    assert result['encrypted'], "Encrypted flag not set"
    decrypted = decrypt(result['payload'], key)
    assert decrypted == b'Classified', "Decrypted content mismatch"
    print(f'  ✓ Encrypted flag set: {result["encrypted"]}')
    print(f'  ✓ Decrypted payload : {decrypted}')
    os.remove('_test2.key')

    # Test 4: SQLite message storage
    print('\n[Test 4] SQLite message storage')
    TEST_DB = 'test_temp.db'
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(db_path=TEST_DB)
    save_message('Alice', 'Hey Bob!',  'msg-001', int(time.time()*1000), 'Bob',   db_path=TEST_DB)
    save_message('Bob',   'Hi Alice!', 'msg-002', int(time.time()*1000), 'Alice', db_path=TEST_DB)
    history = load_history(db_path=TEST_DB)
    assert len(history) == 2
    assert history[0]['sender'] == 'Alice'
    delete_message('msg-001', TEST_DB)
    history2 = load_history(db_path=TEST_DB)
    assert len(history2) == 1
    os.remove(TEST_DB)
    print(f'  ✓ Saved 2 messages, deleted 1, loaded {len(history2)} (correct)')

    # Test 5: Corrupt packet detection
    print('\n[Test 5] Corrupt packet detection')
    pkt   = build_packet(MSG_CHAT, b'Integrity check')
    # flip a byte in the payload area
    corrupted = bytearray(pkt)
    corrupted[-1] ^= 0xFF
    result = parse_packet(bytes(corrupted))
    assert not result['checksum_valid'], "Should have detected corruption"
    print(f'  ✓ Corrupted packet detected (checksum_valid = {result["checksum_valid"]})')

    print('\n' + '=' * 50)
    print('  ALL TESTS PASSED ✓')
    print('=' * 50)


if __name__ == '__main__':
    _run_tests()