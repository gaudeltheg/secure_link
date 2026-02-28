import queue
import socket
import time

from src.network import TCPClient, TCPServer, UDPDiscovery


def _wait_for(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _pick_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_tcp_connect_send_receive_roundtrip() -> None:
    server_recv: "queue.Queue" = queue.Queue()
    client_recv: "queue.Queue" = queue.Queue()
    server = TCPServer(port=0, recv_queue=server_recv, heartbeat_interval=0.2, dead_peer_timeout=2.0)
    server_port = server.start()

    client = TCPClient(
        recv_queue=client_recv,
        reconnect=False,
        heartbeat_interval=0.2,
        dead_peer_timeout=2.0,
    )
    client.start("127.0.0.1", server_port)

    try:
        assert _wait_for(lambda: len(server.peers()) == 1), "server did not accept client"
        client.send_packet("TXT", b"hello-server")
        peer, pkt_type, payload, meta = server_recv.get(timeout=2.0)
        assert pkt_type == "TXT"
        assert payload == b"hello-server"
        assert meta["header_len"] == 32

        server.send_packet(peer, "TXT", b"hello-client")
        c_peer, c_type, c_payload, _ = client_recv.get(timeout=2.0)
        assert c_peer == ("127.0.0.1", server_port)
        assert c_type == "TXT"
        assert c_payload == b"hello-client"
    finally:
        client.stop()
        server.stop()


def test_udp_discovery_peer_seen_event() -> None:
    discovery_port = _pick_udp_port()
    alice_q: "queue.Queue" = queue.Queue()
    bob_q: "queue.Queue" = queue.Queue()

    alice = UDPDiscovery(
        user_name="alice",
        tcp_port=6001,
        logic_in_queue=alice_q,
        discovery_port=discovery_port,
        broadcast_interval=0.1,
        broadcast_addr="127.0.0.1",
    )
    bob = UDPDiscovery(
        user_name="bob",
        tcp_port=6002,
        logic_in_queue=bob_q,
        discovery_port=discovery_port,
        broadcast_interval=0.1,
        broadcast_addr="127.0.0.1",
    )
    bob.start(broadcaster=False, listener=True)
    alice.start(broadcaster=True, listener=False)

    try:
        event = bob_q.get(timeout=2.0)
        assert event["cmd"] == "peer_seen"
        assert event["data"]["user"] == "alice"
        assert event["data"]["port"] == 6001
    finally:
        alice.stop()
        bob.stop()


def test_heartbeat_removes_dead_peer() -> None:
    server_recv: "queue.Queue" = queue.Queue()
    server = TCPServer(port=0, recv_queue=server_recv, heartbeat_interval=0.1, dead_peer_timeout=0.4)
    server_port = server.start()
    client = TCPClient(recv_queue=queue.Queue(), reconnect=False, heartbeat_interval=0.1, dead_peer_timeout=0.4)
    client.start("127.0.0.1", server_port)

    try:
        assert _wait_for(lambda: len(server.peers()) == 1), "client not connected"
        client.stop()
        assert _wait_for(lambda: len(server.peers()) == 0, timeout=3.0), "dead peer not removed"
    finally:
        client.stop()
        server.stop()
