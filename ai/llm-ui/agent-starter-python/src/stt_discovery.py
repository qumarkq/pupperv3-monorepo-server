"""IPv4 LAN discovery for the standalone Whisper service.

The same module is distributed with tools/remote_stt so the Windows service
can run independently of the robot project. The protocol uses only stdlib;
the Pi diagnostic CLI reads settings with the project's existing python-dotenv.
No audio or token is broadcast.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import re
import socket
import time
import uuid
from pathlib import Path

PROTOCOL = "pupper-stt-discovery-v1"
DEFAULT_PORT = 8009
DEFAULT_NAME = "pupper-whisper"
logger = logging.getLogger(__name__)


def validate_settings(name: str, port: int, timeout: float = 3.0) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("STT discovery name must contain 1-64 letters, digits, '_' or '-'.")
    if isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("STT discovery port must be between 1 and 65535.")
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("STT discovery timeout must be in (0, 30] seconds.")


def _proof(token: str, action: str, name: str, nonce: str, port: int = 0, host: str = "") -> str:
    message = f"{PROTOCOL}:{action}:{name}:{nonce}:{port}:{host}".encode()
    return hmac.new(token.encode(), message, hashlib.sha256).hexdigest() if token else ""


def _packet(data: bytes) -> dict | None:
    if len(data) > 1024:
        return None
    try:
        result = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    return result if isinstance(result, dict) else None


def _matches_proof(value: object, expected: str) -> bool:
    # Reject non-ASCII / malformed values before compare_digest.
    return (
        isinstance(value, str) and re.fullmatch(r"(?:[a-f0-9]{64})?", value) is not None
        and hmac.compare_digest(value, expected)
    )


class DiscoveryResponder(asyncio.DatagramProtocol):
    """Answer authenticated, service-specific requests with the HTTP port."""

    def __init__(self, name: str, http_port: int, token: str = "") -> None:
        validate_settings(name, http_port)
        self.name = name
        self.http_port = http_port
        self.token = token
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        request = _packet(data)
        if not request or request.get("protocol") != PROTOCOL:
            return
        nonce = request.get("nonce")
        if (
            request.get("action") != "discover" or request.get("name") != self.name
            or not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce)
        ):
            return
        proof = request.get("proof", "")
        if not _matches_proof(
            proof, _proof(self.token, "discover", self.name, nonce),
        ):
            return
        # Bind signed offers to the source interface so a captured offer cannot
        # redirect a token-bearing HTTP request to a different IPv4 address.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
                route.connect(addr)
                host = route.getsockname()[0]
        except OSError:
            logger.warning("STT discovery could not determine the reply interface.")
            return
        response = {
            "protocol": PROTOCOL, "action": "offer", "name": self.name,
            "nonce": nonce, "http_port": self.http_port, "http_host": host,
            "proof": _proof(self.token, "offer", self.name, nonce, self.http_port, host),
        }
        if self.transport is not None:
            self.transport.sendto(json.dumps(response).encode(), addr)

    def error_received(self, exc: Exception) -> None:
        logger.warning("STT discovery UDP error: %s", type(exc).__name__)


class _Receiver(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.messages: asyncio.Queue[tuple[bytes, tuple[str, int]]] = asyncio.Queue(maxsize=32)
        self.error: Exception | None = None

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) <= 1024 and not self.messages.full():
            self.messages.put_nowait((data, addr))

    def error_received(self, exc: Exception) -> None:
        self.error = exc


async def discover_service(
    *,
    name: str = DEFAULT_NAME,
    port: int = DEFAULT_PORT,
    timeout: float = 3.0,
    token: str = "",
) -> str:
    """Locate one matching service; reject multiple observed endpoints.

    Each invocation performs discovery; the voice client caches a successful URL
    for its lifetime and discovers again only after that client is restarted.
    Replies carry a fresh nonce. Optional HMAC validates discovery messages.
    """
    validate_settings(name, port, timeout)
    loop = asyncio.get_running_loop()
    receiver = _Receiver()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: receiver, local_addr=("0.0.0.0", 0),
        family=socket.AF_INET, allow_broadcast=True,
    )
    nonce = uuid.uuid4().hex
    request = json.dumps({
        "protocol": PROTOCOL, "action": "discover", "name": name, "nonce": nonce,
        "proof": _proof(token, "discover", name, nonce),
    }).encode()
    deadline = time.monotonic() + timeout
    next_send = 0.0
    settle_deadline: float | None = None
    candidates: set[str] = set()
    try:
        while True:
            now = time.monotonic()
            end = min(deadline, settle_deadline) if settle_deadline is not None else deadline
            if now >= end:
                break
            if receiver.error is not None:
                raise OSError("STT discovery broadcast failed.") from receiver.error
            if now >= next_send and not candidates:
                transport.sendto(request, ("255.255.255.255", port))
                next_send = now + 0.5
            wait = min(end - now, 0.5)
            try:
                raw, addr = await asyncio.wait_for(receiver.messages.get(), timeout=wait)
            except asyncio.TimeoutError:
                continue
            response = _packet(raw)
            if not response or (
                response.get("protocol") != PROTOCOL or response.get("action") != "offer"
                or response.get("name") != name or response.get("nonce") != nonce
            ):
                continue
            http_port = response.get("http_port")
            host = response.get("http_host")
            proof = response.get("proof", "")
            if (
                not isinstance(http_port, int) or isinstance(http_port, bool)
                or not 1 <= http_port <= 65535 or host != addr[0] or not isinstance(proof, str)
                or not _matches_proof(
                    proof, _proof(token, "offer", name, nonce, http_port, host),
                )
            ):
                continue
            # Use the responder's observed IPv4 address, not an arbitrary offered URL.
            candidates.add(f"http://{addr[0]}:{http_port}")
            if settle_deadline is None:
                settle_deadline = time.monotonic() + 0.25
        if len(candidates) > 1:
            raise RuntimeError(
                "Multiple STT services replied with the same discovery name. "
                "Set distinct service names or use a manual REMOTE_STT_URL."
            )
        if not candidates:
            if receiver.error is not None:
                raise OSError("STT discovery broadcast failed.") from receiver.error
            raise TimeoutError(
                "No matching Windows STT service found. Check server startup, "
                "same LAN, discovery name/token, UDP firewall and Wi-Fi isolation."
            )
        return next(iter(candidates))
    finally:
        transport.close()


def main() -> None:
    # The Pi diagnostic command reads the same settings as the voice agent.
    env_file = Path(__file__).resolve().parent.parent / ".env.local"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)
    parser = argparse.ArgumentParser(description="Find the Windows Whisper URL on this LAN.")
    parser.add_argument("--name", default=os.getenv("REMOTE_STT_DISCOVERY_NAME", DEFAULT_NAME))
    parser.add_argument("--port", type=int, default=int(os.getenv("REMOTE_STT_DISCOVERY_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("REMOTE_STT_DISCOVERY_TIMEOUT", "3")))
    args = parser.parse_args()
    try:
        url = asyncio.run(discover_service(
            name=args.name, port=args.port, timeout=args.timeout,
            token=os.getenv("REMOTE_STT_TOKEN", ""),
        ))
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"STT discovery failed: {exc}\n")
    print(url)


if __name__ == "__main__":
    main()
