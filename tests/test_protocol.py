import socket

import pytest

from src.protocol import HEADER_LEN, build_packet, parse_header, recv_exact, recv_packet


def test_build_packet_roundtrip() -> None:
    payload = b"hello-secure-link"
    packet = build_packet("TXT", payload, flags=1, message_id=123)
    header = parse_header(packet[:HEADER_LEN])
    assert header["type"] == "TXT"
    assert header["payload_size"] == len(payload)
    assert packet[HEADER_LEN:] == payload


def test_recv_exact_reads_full_buffer() -> None:
    left, right = socket.socketpair()
    try:
        right.sendall(b"abc")
        right.sendall(b"defghi")
        assert recv_exact(left, 9) == b"abcdefghi"
    finally:
        left.close()
        right.close()


def test_recv_packet_detects_checksum_corruption() -> None:
    left, right = socket.socketpair()
    try:
        packet = bytearray(build_packet("TXT", b"checksum"))
        packet[-1] ^= 0xFF
        right.sendall(packet)
        with pytest.raises(ValueError, match="checksum mismatch"):
            recv_packet(left)
    finally:
        left.close()
        right.close()
