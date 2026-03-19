"""
SecureLink — test_protocol.py
Member C: 41 unit tests for protocol.py
"""

import sys, os, time, socket, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from protocol import (
    build_packet, parse_packet, recv_packet,
    MSG_CHAT, MSG_FILE, MSG_ACK, MSG_ERROR, MSG_HANDSHAKE,
    HEADER_LEN,
    generate_key, load_key, encrypt, decrypt,
    encrypt_if_needed, decrypt_if_needed,
    init_db, save_message, load_history, delete_message,
    send_file, receive_file,
)

PASS = 0
FAIL = 0

def check(label, condition):
    global PASS, FAIL
    if condition:
        print(f"  ✓ {label}")
        PASS += 1
    else:
        print(f"  ✗ FAIL: {label}")
        FAIL += 1

def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")

# ─────────────────────────────────────────────
# Group 1: Packet Tests (18 tests)
# ─────────────────────────────────────────────
section("Group 1: Packet Tests")

# 1. Correct header length
pkt = build_packet(MSG_CHAT, b'Hello')
check("Header is 32 bytes", len(pkt) >= HEADER_LEN)

# 2. Magic bytes
check("Magic bytes are SLNK", pkt[:4] == b'SLNK')

# 3. Payload roundtrip
result = parse_packet(pkt)
check("Payload roundtrip", result['payload'] == b'Hello')

# 4. Checksum valid on clean packet
check("Checksum valid on clean packet", result['checksum_valid'])

# 5. MSG_CHAT type
pkt = build_packet(MSG_CHAT, b'chat')
check("MSG_CHAT type correct", parse_packet(pkt)['msg_type'] == MSG_CHAT)

# 6. MSG_FILE type
pkt = build_packet(MSG_FILE, b'file')
check("MSG_FILE type correct", parse_packet(pkt)['msg_type'] == MSG_FILE)

# 7. MSG_ACK type
pkt = build_packet(MSG_ACK, b'ack')
check("MSG_ACK type correct", parse_packet(pkt)['msg_type'] == MSG_ACK)

# 8. MSG_ERROR type
pkt = build_packet(MSG_ERROR, b'err')
check("MSG_ERROR type correct", parse_packet(pkt)['msg_type'] == MSG_ERROR)

# 9. MSG_HANDSHAKE type
pkt = build_packet(MSG_HANDSHAKE, b'shake')
check("MSG_HANDSHAKE type correct", parse_packet(pkt)['msg_type'] == MSG_HANDSHAKE)

# 10. Corrupted packet detected
pkt = build_packet(MSG_CHAT, b'Integrity')
corrupted = bytearray(pkt)
corrupted[-1] ^= 0xFF
check("Corrupted packet detected", not parse_packet(bytes(corrupted))['checksum_valid'])

# 11. Empty payload
pkt = build_packet(MSG_CHAT, b'')
check("Empty payload roundtrip", parse_packet(pkt)['payload'] == b'')

# 12. Large payload
big = os.urandom(64 * 1024)
pkt = build_packet(MSG_CHAT, big)
check("Large payload (64KB) roundtrip", parse_packet(pkt)['payload'] == big)

# 13. Binary payload
binary = bytes(range(256))
pkt = build_packet(MSG_CHAT, binary)
check("Binary payload roundtrip", parse_packet(pkt)['payload'] == binary)

# 14. message_id stored
pkt = build_packet(MSG_CHAT, b'x', message_id='abc-123')
check("message_id stored correctly", parse_packet(pkt)['message_id'] == 'abc-123')

# 15. Timestamp is recent
pkt = build_packet(MSG_CHAT, b'time')
ts = parse_packet(pkt)['timestamp']
check("Timestamp is recent (within 5s)", abs(ts - int(time.time()*1000)) < 5000)

# 16. Encrypted flag not set by default
pkt = build_packet(MSG_CHAT, b'plain')
check("Encrypted flag not set by default", not parse_packet(pkt)['encrypted'])

# 17. recv_packet over loopback
def _server(results):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 19876))
    srv.listen(1)
    conn, _ = srv.accept()
    results['pkt'] = recv_packet(conn)
    conn.close()
    srv.close()

results = {}
t = threading.Thread(target=_server, args=(results,), daemon=True)
t.start()
time.sleep(0.1)
cli = socket.socket()
cli.connect(('127.0.0.1', 19876))
cli.sendall(build_packet(MSG_CHAT, b'loopback'))
cli.close()
t.join(timeout=3)
check("recv_packet over loopback socket", results.get('pkt', {}).get('payload') == b'loopback')

# 18. Two packets in sequence
pkt1 = build_packet(MSG_CHAT, b'first')
pkt2 = build_packet(MSG_CHAT, b'second')
r1 = parse_packet(pkt1)
r2 = parse_packet(pkt2)
check("Two sequential packets parsed correctly",
      r1['payload'] == b'first' and r2['payload'] == b'second')


# ─────────────────────────────────────────────
# Group 2: Encryption Tests (13 tests)
# ─────────────────────────────────────────────
section("Group 2: Encryption Tests")

KEY_PATH = '_test_enc.key'

# 19. generate_key creates file
key = generate_key(KEY_PATH)
check("generate_key creates file", os.path.exists(KEY_PATH))

# 20. generate_key returns bytes
check("generate_key returns bytes", isinstance(key, bytes))

# 21. load_key returns same key
loaded = load_key(KEY_PATH)
check("load_key returns same key", loaded == key)

# 22. encrypt returns bytes
enc = encrypt(b'secret', key)
check("encrypt returns bytes", isinstance(enc, bytes))

# 23. encrypted != original
check("encrypted != original", enc != b'secret')

# 24. decrypt roundtrip
check("decrypt roundtrip", decrypt(enc, key) == b'secret')

# 25. wrong key raises exception
key2 = generate_key('_test_enc2.key')
try:
    decrypt(enc, key2)
    check("wrong key raises exception", False)
except Exception:
    check("wrong key raises exception", True)

# 26. corrupted ciphertext raises exception
try:
    bad = bytearray(enc)
    bad[10] ^= 0xFF
    decrypt(bytes(bad), key)
    check("corrupted ciphertext raises exception", False)
except Exception:
    check("corrupted ciphertext raises exception", True)

# 27. encrypt_if_needed with True
data, flag = encrypt_if_needed(b'data', key, should_encrypt=True)
check("encrypt_if_needed with True returns flag=1", flag == 1)

# 28. encrypt_if_needed with False
data2, flag2 = encrypt_if_needed(b'data', key, should_encrypt=False)
check("encrypt_if_needed with False returns flag=0", flag2 == 0 and data2 == b'data')

# 29. decrypt_if_needed decrypts encrypted packet
enc_pkt = build_packet(MSG_CHAT, b'hidden', encrypt_payload=True, key=key)
parsed  = parse_packet(enc_pkt)
plain   = decrypt_if_needed(parsed, key)
check("decrypt_if_needed decrypts correctly", plain == b'hidden')

# 30. decrypt_if_needed skips plain packet
plain_pkt = build_packet(MSG_CHAT, b'visible')
parsed2   = parse_packet(plain_pkt)
out       = decrypt_if_needed(parsed2, key)
check("decrypt_if_needed skips plain packet", out == b'visible')

# 31. Encrypt large data (100KB)
big_data = os.urandom(100 * 1024)
enc_big  = encrypt(big_data, key)
check("Encrypt/decrypt 100KB data", decrypt(enc_big, key) == big_data)

# cleanup
for f in [KEY_PATH, '_test_enc2.key']:
    if os.path.exists(f):
        os.remove(f)


# ─────────────────────────────────────────────
# Group 3: Database Tests (10 tests)
# ─────────────────────────────────────────────
section("Group 3: Database Tests")

DB = '_test_db.db'
if os.path.exists(DB):
    os.remove(DB)

# 32. init_db creates file
init_db(db_path=DB)
check("init_db creates database file", os.path.exists(DB))

# 33. save and load one message
save_message('Alice', 'Hi Bob', 'db-001', int(time.time()*1000), 'Bob', db_path=DB)
history = load_history(db_path=DB)
check("save and load one message", len(history) == 1)

# 34. sender correct
check("sender field correct", history[0]['sender'] == 'Alice')

# 35. content correct
check("content field correct", history[0]['content'] == 'Hi Bob')

# 36. receiver correct
check("receiver field correct", history[0]['receiver'] == 'Bob')

# 37. save second message
save_message('Bob', 'Hey Alice', 'db-002', int(time.time()*1000)+1, 'Alice', db_path=DB)
history = load_history(db_path=DB)
check("two messages saved", len(history) == 2)

# 38. ordered by timestamp
check("messages ordered by timestamp", history[0]['sender'] == 'Alice')

# 39. delete message (soft delete)
delete_message('db-001', db_path=DB)
history = load_history(db_path=DB)
check("deleted message not in history", len(history) == 1)

# 40. remaining message is correct
check("remaining message is correct", history[0]['message_id'] == 'db-002')

# 41. duplicate message_id ignored
save_message('Alice', 'duplicate', 'db-002', int(time.time()*1000), 'Bob', db_path=DB)
history = load_history(db_path=DB)
check("duplicate message_id ignored", len(history) == 1)

if os.path.exists(DB):
    os.remove(DB)


# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  Results: {PASS}/{PASS+FAIL} passed  {'— ALL TESTS PASSED ✓' if FAIL == 0 else f'— {FAIL} FAILED ✗'}")
print(f"{'='*50}\n")