"""Shared wire protocol utilities for SecureLink."""

from __future__ import annotations

import binascii
import socket
import struct
import time
from typing import Any

MAGIC = b"SLNK"
HEADER_LEN = 32
CHUNK_SIZE = 4096
PROTOCOL_VERSION = 1

TYPE_TO_CODE = {
    "TXT": 1,
    "FIL": 2,
    "DSC": 3,
    "AUT": 4,
    "META": 5,
    "ACK": 6,
    "ERR": 7,
}
CODE_TO_TYPE = {value: key for key, value in TYPE_TO_CODE.items()}

FLAG_ENCRYPTED = 1 << 0
FLAG_SELF_DESTRUCT = 1 << 1
FLAG_ACK_REQUIRED = 1 << 2


def make_header(
    packet_type: str,
    payload_size: int,
    *,
    flags: int = 0,
    message_id: int = 0,
    timestamp: int | None = None,
    version: int = PROTOCOL_VERSION,
    checksum: int = 0,
) -> bytes:
    """Build a fixed-size 32-byte SecureLink header."""
    if packet_type not in TYPE_TO_CODE:
        raise ValueError(f"unknown packet type: {packet_type}")
    if payload_size < 0:
        raise ValueError("payload_size must be >= 0")
    if timestamp is None:
        timestamp = int(time.time())
    return struct.pack(
        "!4sBBBBQQII",
        MAGIC,
        version,
        TYPE_TO_CODE[packet_type],
        flags & 0xFF,
        0,  # reserved
        message_id & 0xFFFFFFFFFFFFFFFF,
        timestamp & 0xFFFFFFFFFFFFFFFF,
        payload_size & 0xFFFFFFFF,
        checksum & 0xFFFFFFFF,
    )


def parse_header(header_bytes: bytes) -> dict[str, Any]:
    """Parse a 32-byte SecureLink header."""
    if len(header_bytes) != HEADER_LEN:
        raise ValueError(f"invalid header length: {len(header_bytes)}")

    magic, version, type_code, flags, _reserved, message_id, timestamp, size, checksum = struct.unpack(
        "!4sBBBBQQII",
        header_bytes,
    )
    if magic != MAGIC:
        raise ValueError(f"invalid magic: {magic!r}")

    pkt_type = CODE_TO_TYPE.get(type_code, f"UNKNOWN_{type_code}")
    return {
        "magic": magic,
        "version": version,
        "type_code": type_code,
        "type": pkt_type,
        "flags": flags,
        "message_id": message_id,
        "timestamp": timestamp,
        "payload_size": size,
        "checksum": checksum,
    }


def build_packet(
    packet_type: str,
    payload: bytes,
    *,
    flags: int = 0,
    message_id: int = 0,
    timestamp: int | None = None,
    version: int = PROTOCOL_VERSION,
) -> bytes:
    """Build header + payload with payload checksum."""
    checksum = binascii.crc32(payload) & 0xFFFFFFFF
    header = make_header(
        packet_type,
        len(payload),
        flags=flags,
        message_id=message_id,
        timestamp=timestamp,
        version=version,
        checksum=checksum,
    )
    return header + payload


def recv_exact(sock: socket.socket, n_bytes: int) -> bytes:
    """Receive exactly n_bytes from a stream socket or raise ConnectionError."""
    if n_bytes < 0:
        raise ValueError("n_bytes must be >= 0")
    buffer = bytearray()
    while len(buffer) < n_bytes:
        chunk = sock.recv(n_bytes - len(buffer))
        if not chunk:
            raise ConnectionError("socket closed while receiving data")
        buffer.extend(chunk)
    return bytes(buffer)


def recv_packet(sock: socket.socket) -> tuple[dict[str, Any], bytes]:
    """Read a full packet from a stream socket and validate checksum."""
    header_bytes = recv_exact(sock, HEADER_LEN)
    header = parse_header(header_bytes)
    payload = recv_exact(sock, header["payload_size"])
    expected = header["checksum"]
    actual = binascii.crc32(payload) & 0xFFFFFFFF
    if expected != actual:
        raise ValueError(f"checksum mismatch: expected={expected} actual={actual}")
    return header, payload
