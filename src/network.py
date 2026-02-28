"""Transport layer: TCP engine, UDP discovery, heartbeat, reconnect."""

from __future__ import annotations

import json
import logging
import queue
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .protocol import HEADER_LEN, build_packet, parse_header, recv_packet

PeerID = tuple[str, int]
RecvItem = tuple[PeerID, str, bytes, dict[str, Any]]


def _default_logger() -> logging.Logger:
    logger = logging.getLogger("secure_link.network")
    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    return logger


@dataclass
class Connection:
    """Single TCP connection with dedicated sender and receiver threads."""

    sock: socket.socket
    peer_id: PeerID
    recv_queue: "queue.Queue[RecvItem]"
    on_disconnect: Callable[[PeerID], None]
    logger: logging.Logger
    heartbeat_timeout: float
    send_queue: "queue.Queue[bytes]" = field(default_factory=queue.Queue)
    alive: threading.Event = field(default_factory=threading.Event)
    last_seen: float = field(default_factory=time.monotonic)
    last_pong: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.alive.set()
        self._send_thread = threading.Thread(
            target=self._send_loop,
            name=f"send-{self.peer_id[0]}:{self.peer_id[1]}",
            daemon=True,
        )
        self._recv_thread = threading.Thread(
            target=self._recv_loop,
            name=f"recv-{self.peer_id[0]}:{self.peer_id[1]}",
            daemon=True,
        )
        self._send_thread.start()
        self._recv_thread.start()

    def enqueue(self, packet_bytes: bytes) -> None:
        if not self.alive.is_set():
            raise ConnectionError(f"peer {self.peer_id} is disconnected")
        self.send_queue.put(packet_bytes)

    def send_packet(self, packet_type: str, payload: bytes, *, flags: int = 0) -> None:
        self.enqueue(build_packet(packet_type, payload, flags=flags))

    def close(self) -> None:
        if not self.alive.is_set():
            return
        self.alive.clear()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _send_loop(self) -> None:
        try:
            while self.alive.is_set():
                try:
                    packet = self.send_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                self.sock.sendall(packet)
        except OSError as exc:
            self.logger.info("sender loop ended for %s (%s)", self.peer_id, exc)
        finally:
            self.close()
            self.on_disconnect(self.peer_id)

    def _recv_loop(self) -> None:
        try:
            while self.alive.is_set():
                header, payload = recv_packet(self.sock)
                self.last_seen = time.monotonic()
                pkt_type = header["type"]

                if pkt_type == "META" and payload == b"PING":
                    self.send_packet("META", b"PONG")
                    continue
                if pkt_type == "META" and payload == b"PONG":
                    self.last_pong = time.monotonic()
                    continue

                self.recv_queue.put(
                    (
                        self.peer_id,
                        pkt_type,
                        payload,
                        {
                            "flags": header["flags"],
                            "message_id": header["message_id"],
                            "timestamp": header["timestamp"],
                            "header_len": HEADER_LEN,
                            "encrypted": bool(header["flags"] & 0x01),
                        },
                    )
                )
        except (ConnectionError, OSError, ValueError) as exc:
            self.logger.info("receiver loop ended for %s (%s)", self.peer_id, exc)
        finally:
            self.close()
            self.on_disconnect(self.peer_id)


class TCPServer:
    """TCP server that exposes queue-based APIs for the logic layer."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        *,
        recv_queue: "queue.Queue[RecvItem] | None" = None,
        heartbeat_interval: float = 10.0,
        dead_peer_timeout: float = 30.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.recv_queue = recv_queue or queue.Queue()
        self.heartbeat_interval = heartbeat_interval
        self.dead_peer_timeout = dead_peer_timeout
        self.logger = logger or _default_logger()
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._connections: dict[PeerID, Connection] = {}
        self._running = threading.Event()
        self._accept_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

    def start(self) -> int:
        if self._running.is_set():
            return self.port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen()
        self.port = sock.getsockname()[1]
        self._sock = sock
        self._running.set()
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._accept_thread.start()
        self._heartbeat_thread.start()
        self.logger.info("tcp server started on %s:%s", self.host, self.port)
        return self.port

    def stop(self) -> None:
        if not self._running.is_set():
            return
        self._running.clear()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        with self._lock:
            peers = list(self._connections.values())
        for conn in peers:
            conn.close()
        self.logger.info("tcp server stopped")

    def peers(self) -> list[PeerID]:
        with self._lock:
            return list(self._connections.keys())

    def send_bytes(self, peer: PeerID, packet_bytes: bytes) -> None:
        with self._lock:
            conn = self._connections.get(peer)
        if conn is None:
            raise KeyError(f"unknown peer: {peer}")
        conn.enqueue(packet_bytes)

    def send_packet(self, peer: PeerID, packet_type: str, payload: bytes, *, flags: int = 0) -> None:
        self.send_bytes(peer, build_packet(packet_type, payload, flags=flags))

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while self._running.is_set():
            try:
                client_sock, addr = self._sock.accept()
            except OSError:
                break
            peer_id = (addr[0], addr[1])
            self.logger.info("accepted tcp connection from %s", peer_id)
            conn = Connection(
                sock=client_sock,
                peer_id=peer_id,
                recv_queue=self.recv_queue,
                on_disconnect=self._drop_peer,
                logger=self.logger,
                heartbeat_timeout=self.dead_peer_timeout,
            )
            with self._lock:
                self._connections[peer_id] = conn

    def _drop_peer(self, peer_id: PeerID) -> None:
        with self._lock:
            conn = self._connections.pop(peer_id, None)
        if conn is not None:
            conn.close()
            self.logger.info("peer removed: %s", peer_id)

    def _heartbeat_loop(self) -> None:
        while self._running.is_set():
            time.sleep(self.heartbeat_interval)
            now = time.monotonic()
            stale_peers: list[PeerID] = []
            with self._lock:
                items = list(self._connections.items())
            for peer_id, conn in items:
                if not conn.alive.is_set():
                    stale_peers.append(peer_id)
                    continue
                if now - conn.last_pong > self.dead_peer_timeout:
                    stale_peers.append(peer_id)
                    continue
                try:
                    conn.send_packet("META", b"PING")
                except (ConnectionError, OSError):
                    stale_peers.append(peer_id)
            for peer in stale_peers:
                self._drop_peer(peer)


class TCPClient:
    """TCP client with optional reconnect-backoff loop."""

    def __init__(
        self,
        *,
        recv_queue: "queue.Queue[RecvItem] | None" = None,
        heartbeat_interval: float = 10.0,
        dead_peer_timeout: float = 30.0,
        reconnect: bool = True,
        reconnect_max_backoff: float = 10.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.recv_queue = recv_queue or queue.Queue()
        self.heartbeat_interval = heartbeat_interval
        self.dead_peer_timeout = dead_peer_timeout
        self.reconnect = reconnect
        self.reconnect_max_backoff = reconnect_max_backoff
        self.logger = logger or _default_logger()

        self._lock = threading.Lock()
        self._conn: Connection | None = None
        self._target: PeerID | None = None
        self._running = threading.Event()
        self._reconnect_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._needs_reconnect = threading.Event()

    def connect_to(self, ip: str, port: int) -> PeerID:
        self._target = (ip, port)
        return self._connect_once(ip, port)

    def start(self, ip: str, port: int) -> None:
        self._running.set()
        self.connect_to(ip, port)
        if self.reconnect and self._reconnect_thread is None:
            self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self._reconnect_thread.start()
        if self._heartbeat_thread is None:
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

    def stop(self) -> None:
        self._running.clear()
        self._needs_reconnect.clear()
        with self._lock:
            conn = self._conn
            self._conn = None
        if conn is not None:
            conn.close()

    def send_bytes(self, packet_bytes: bytes) -> None:
        with self._lock:
            conn = self._conn
        if conn is None:
            raise ConnectionError("client is not connected")
        conn.enqueue(packet_bytes)

    def send_packet(self, packet_type: str, payload: bytes, *, flags: int = 0) -> None:
        self.send_bytes(build_packet(packet_type, payload, flags=flags))

    def peer_id(self) -> PeerID | None:
        with self._lock:
            return self._conn.peer_id if self._conn else None

    def _connect_once(self, ip: str, port: int) -> PeerID:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((ip, port))
        sock.settimeout(None)
        peer_id = (ip, port)
        conn = Connection(
            sock=sock,
            peer_id=peer_id,
            recv_queue=self.recv_queue,
            on_disconnect=self._on_disconnect,
            logger=self.logger,
            heartbeat_timeout=self.dead_peer_timeout,
        )
        with self._lock:
            old = self._conn
            self._conn = conn
        if old is not None and old is not conn:
            old.close()
        self.logger.info("tcp client connected to %s", peer_id)
        return peer_id

    def _on_disconnect(self, _peer: PeerID) -> None:
        with self._lock:
            self._conn = None
        if self.reconnect and self._running.is_set():
            self._needs_reconnect.set()

    def _reconnect_loop(self) -> None:
        backoff = 0.5
        while self._running.is_set():
            if not self._needs_reconnect.wait(timeout=0.5):
                continue
            target = self._target
            if target is None:
                continue
            while self._running.is_set():
                try:
                    self._connect_once(*target)
                    self._needs_reconnect.clear()
                    backoff = 0.5
                    break
                except OSError as exc:
                    self.logger.info("reconnect failed to %s (%s)", target, exc)
                    time.sleep(backoff)
                    backoff = min(self.reconnect_max_backoff, backoff * 2)

    def _heartbeat_loop(self) -> None:
        while self._running.is_set():
            time.sleep(self.heartbeat_interval)
            with self._lock:
                conn = self._conn
            if conn is None:
                continue
            now = time.monotonic()
            if now - conn.last_pong > self.dead_peer_timeout:
                conn.close()
                self._on_disconnect(conn.peer_id)
                continue
            try:
                conn.send_packet("META", b"PING")
            except (ConnectionError, OSError):
                conn.close()
                self._on_disconnect(conn.peer_id)


class UDPDiscovery:
    """UDP beacon broadcaster/listener for automatic peer discovery."""

    def __init__(
        self,
        user_name: str,
        tcp_port: int,
        logic_in_queue: "queue.Queue[dict[str, Any]]",
        *,
        discovery_port: int = 5556,
        broadcast_interval: float = 2.0,
        peer_ttl: float = 10.0,
        broadcast_addr: str = "255.255.255.255",
        logger: logging.Logger | None = None,
    ) -> None:
        self.user_name = user_name
        self.tcp_port = tcp_port
        self.logic_in_queue = logic_in_queue
        self.discovery_port = discovery_port
        self.broadcast_interval = broadcast_interval
        self.peer_ttl = peer_ttl
        self.broadcast_addr = broadcast_addr
        self.logger = logger or _default_logger()
        self.instance_id = str(uuid.uuid4())

        self._running = threading.Event()
        self._broadcast_thread: threading.Thread | None = None
        self._listen_thread: threading.Thread | None = None
        self._peers_lock = threading.Lock()
        self._peers: dict[PeerID, dict[str, Any]] = {}

    def start(self, *, broadcaster: bool = True, listener: bool = True) -> None:
        self._running.set()
        if broadcaster and self._broadcast_thread is None:
            self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
            self._broadcast_thread.start()
        if listener and self._listen_thread is None:
            self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listen_thread.start()

    def stop(self) -> None:
        self._running.clear()

    def peers(self) -> dict[PeerID, dict[str, Any]]:
        cutoff = time.monotonic() - self.peer_ttl
        with self._peers_lock:
            stale = [peer for peer, info in self._peers.items() if info["last_seen"] < cutoff]
            for peer in stale:
                self._peers.pop(peer, None)
            return dict(self._peers)

    def _broadcast_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload_template = {
            "user": self.user_name,
            "port": self.tcp_port,
            "instance_id": self.instance_id,
        }
        while self._running.is_set():
            try:
                payload = json.dumps(payload_template).encode("utf-8")
                packet = build_packet("DSC", payload)
                sock.sendto(packet, (self.broadcast_addr, self.discovery_port))
            except OSError as exc:
                self.logger.info("udp broadcast failed (%s)", exc)
            time.sleep(self.broadcast_interval)
        sock.close()

    def _listen_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.discovery_port))
        while self._running.is_set():
            try:
                datagram, addr = sock.recvfrom(65535)
            except OSError:
                break
            if len(datagram) < HEADER_LEN:
                continue
            try:
                header = parse_header(datagram[:HEADER_LEN])
            except ValueError:
                continue
            if header["type"] != "DSC":
                continue
            payload = datagram[HEADER_LEN : HEADER_LEN + header["payload_size"]]
            try:
                payload_data = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if payload_data.get("instance_id") == self.instance_id:
                continue

            peer_ip = addr[0]
            peer_port = int(payload_data.get("port", 0))
            peer_id = (peer_ip, peer_port)
            peer_info = {
                "user": payload_data.get("user", "unknown"),
                "port": peer_port,
                "last_seen": time.monotonic(),
                "ip": peer_ip,
                "instance_id": payload_data.get("instance_id"),
                "status": "active",
            }
            with self._peers_lock:
                self._peers[peer_id] = peer_info
            self.logic_in_queue.put({"cmd": "peer_seen", "ip": peer_ip, "data": peer_info})
        sock.close()


def windows_firewall_instructions(app_name: str = "SecureLink", tcp_port: int = 5000, udp_port: int = 5556) -> str:
    """Return copy-paste guidance; caller may display this in UI/docs."""
    return (
        f'netsh advfirewall firewall add rule name="{app_name} TCP" '
        f"dir=in action=allow protocol=TCP localport={tcp_port}\n"
        f'netsh advfirewall firewall add rule name="{app_name} UDP" '
        f"dir=in action=allow protocol=UDP localport={udp_port}"
    )
