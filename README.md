# secure_link
Implementation of LAN, SecLink is a lightweight, privacy-focused chat application that ensures secure communication over local networks. Built with Python, it features end-to-end encryption, auto-discovery of peers, and secure file transfer capabilities, ensuring your data never leaves your control.

## Network layer APIs

- `src/network.py::TCPServer`
  - `start() -> port`
  - `send_bytes(peer_id, packet_bytes)`
  - `send_packet(peer_id, packet_type, payload, flags=0)`
  - `recv_queue` emits `(peer_id, pkt_type, payload_bytes, extra_meta_dict)`
- `src/network.py::TCPClient`
  - `start(ip, port)` with reconnect backoff
  - `send_bytes(packet_bytes)`
  - `send_packet(packet_type, payload, flags=0)`
- `src/network.py::UDPDiscovery`
  - Broadcaster: emits DSC beacon every 2s by default on UDP `5556`
  - Listener: posts `{"cmd":"peer_seen","ip":..., "data":...}` into `logic_in_queue`

Shared protocol constants/utilities are in `src/protocol.py`:
- `HEADER_LEN = 32`
- `CHUNK_SIZE = 4096`
- `recv_exact(sock, n)`
- `build_packet(...)`, `parse_header(...)`, `recv_packet(...)`
