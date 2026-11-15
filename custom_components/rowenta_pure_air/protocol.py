"""Protocol layer for the Rowenta Intense Pure Air Connect (Broadlink module 0x4f9a "supor_air").

It imports nothing from Home Assistant, so it can be tested on its own.

How it works (verified against a real PU4080):
  * The Broadlink command 0x6A is used with the payload ``[length (2 B, little-endian)] + UART frame``.
  * The MCU UART frame is ``FF FF | len (2 B, BE) | cmd | sn | 00 00 | payload | checksum``;
    ``len`` covers ``cmd..checksum``, the checksum is the sum modulo 256 of ``len..payload`` and,
    after the ``FF FF`` header, every ``FF`` in the body is sent as ``FF 55``.
  * Write: cmd 03 with a 42-byte payload ``01 | mask (2 B, BE) | W | N (38 B)``.
    Known masks: 0x0004 power, 0x0008 mode, 0x2000 light.
  * Read: cmd 03 with payload ``02``; the reply (cmd 04) carries 34 status bytes.
UART protocol documentation: project acvx93/rowenta-pure-air-cloud-rescue.
"""
from __future__ import annotations

import ipaddress
import logging
import struct
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEVTYPE = 0x4F9A
BROADLINK_COMMAND = 0x6A

CMD_INFO = 0x01
CMD_HEARTBEAT = 0x07
CMD_RW = 0x03
REPLY_RW = 0x04
ACTION_READ = 0x02
ACTION_STATUS = 0x03
STATUS_LEN = 34

MASK_POWER = 0x0004
MASK_MODE = 0x0008
MASK_LIGHT = 0x2000

MODES: dict[int, str] = {1: "silent", 2: "night", 3: "auto", 4: "turbo"}
MODE_IDS: dict[str, int] = {name: ident for ident, name in MODES.items()}
LIGHTS: dict[int, str] = {0: "on", 1: "dim", 2: "off"}
LIGHT_IDS: dict[str, int] = {name: ident for ident, name in LIGHTS.items()}

# Positions (within the 34 status bytes) of four 16-bit counters.
# 1000 right after resetting the filter with the physical button, then it decreases with use.
# The order of the filters is NOT confirmed.
COUNTER_OFFSETS = (9, 13, 17, 21)


class RowentaError(Exception):
    """Generic communication error with the purifier."""


class DeviceError(RowentaError):
    """The Broadlink module returned an error code."""


class ProtocolError(RowentaError):
    """Response with an unexpected format."""


class UnsupportedDeviceError(RowentaError):
    """The device is not a supported Rowenta purifier."""


# --------------------------------------------------------------------------- frames
def uart_frame(cmd: int, sn: int, payload: bytes = b"") -> bytes:
    """Build an MCU UART frame, with checksum and 0xFF escaping."""
    body = bytes([cmd, sn, 0, 0]) + bytes(payload)
    head = struct.pack(">H", len(body) + 1)
    checksum = sum(head + body) & 0xFF
    return b"\xff\xff" + (head + body + bytes([checksum])).replace(b"\xff", b"\xff\x55")


def write_payload(mask: int, w: int = 0, n0: int = 3, n6: int = 0) -> bytes:
    """Write payload (cmd 03). Only the fields included in the mask are applied."""
    n = bytearray([2] * 38)
    n[0] = n0
    n[6] = n6
    return bytes([1]) + struct.pack(">H", mask) + bytes([w]) + bytes(n)


def wrap_tunnel(frame: bytes) -> bytes:
    """Length prefix (little-endian) expected by the Broadlink 0x6A command."""
    return struct.pack("<H", len(frame)) + frame


def unwrap_tunnel(payload: bytes) -> bytes:
    """Extract ``cmd sn flags payload checksum`` from the decrypted response, validating the checksum."""
    if len(payload) < 4:
        raise ProtocolError("response too short")
    length = struct.unpack("<H", payload[:2])[0]
    raw = payload[2 : 2 + length]
    if raw[:2] != b"\xff\xff":
        raise ProtocolError("missing FF FF header")
    body = raw[2:].replace(b"\xff\x55", b"\xff")
    if len(body) < 3:
        raise ProtocolError("truncated frame")
    frame_len = struct.unpack(">H", body[:2])[0]
    frame = body[2 : 2 + frame_len]
    if len(frame) != frame_len or frame_len < 5:
        raise ProtocolError("wrong frame length")
    if (sum(body[: 2 + frame_len - 1]) & 0xFF) != frame[-1]:
        raise ProtocolError("wrong checksum")
    return frame


# --------------------------------------------------------------------------- state
@dataclass(frozen=True)
class PurifierState:
    """State read from the purifier."""

    on: bool
    mode: str | None
    speed: int
    pm25: int
    light: str | None
    locked: bool
    counters: tuple[int, int, int, int]


def parse_status(status: bytes) -> PurifierState:
    """Interpret the 34 status bytes."""
    if len(status) != STATUS_LEN:
        raise ProtocolError(f"status of {len(status)} bytes, expected {STATUS_LEN}")
    return PurifierState(
        on=bool(status[1]),
        mode=MODES.get(status[5]),
        speed=status[6],
        pm25=int.from_bytes(status[2:4], "big"),
        light=LIGHTS.get(status[31]),
        locked=bool(status[0] & 0x10),
        counters=tuple(  # type: ignore[arg-type]
            int.from_bytes(status[i : i + 2], "big") for i in COUNTER_OFFSETS
        ),
    )


# --------------------------------------------------------------------------- client
class RowentaClient:
    """Blocking client (use it from a thread/executor)."""

    def __init__(
        self,
        host: str,
        *,
        timeout: float = 5.0,
        hello: Callable[..., Any] | None = None,
        settle: float = 1.0,
    ) -> None:
        self.host = host
        self.mac: str | None = None
        self._timeout = timeout
        self._hello = hello
        self._settle = settle
        self._dev: Any = None
        self._sn = 0x40
        self._lock = threading.RLock()

    # -- connection
    def _connect(self) -> None:
        hello = self._hello
        if hello is None:
            import broadlink  # noqa: PLC0415 - deferred import so it can be tested without the library

            hello = broadlink.hello
        dev = hello(self.host, timeout=self._timeout)
        if dev.devtype != DEVTYPE:
            raise UnsupportedDeviceError(f"devtype {dev.devtype:#06x} not supported")
        dev.auth()
        self._dev = dev
        self.mac = format_mac(dev.mac)
        # The MCU stays silent until it receives a heartbeat or an info request.
        self._tx(CMD_HEARTBEAT)
        self._tx(CMD_INFO)

    def close(self) -> None:
        with self._lock:
            self._dev = None

    def _call(self, fn: Callable[[], Any]) -> Any:
        with self._lock:
            last: Exception | None = None
            for _ in range(2):
                try:
                    if self._dev is None:
                        self._connect()
                    return fn()
                except UnsupportedDeviceError:
                    raise
                except Exception as err:  # noqa: BLE001 - retried after reconnecting
                    last = err
                    self._dev = None
            raise RowentaError(f"{type(last).__name__}: {last}") from last

    # -- transport
    def _tx(self, cmd: int, payload: bytes = b"") -> bytes:
        self._sn = (self._sn + 1) & 0x7F
        frame = uart_frame(cmd, self._sn, payload)
        resp = self._dev.send_packet(BROADLINK_COMMAND, wrap_tunnel(frame))
        if len(resp) < 0x38:
            raise ProtocolError("Broadlink response too short")
        err = struct.unpack("<h", bytes(resp[0x22:0x24]))[0]
        if err:
            raise DeviceError(f"Broadlink error {err}")
        return unwrap_tunnel(self._dev.decrypt(bytes(resp[0x38:])))

    # -- operations
    def _read_state(self) -> PurifierState:
        # The module sometimes interleaves its own notices (cmd 0E/08): they are discarded and the read is retried.
        for _ in range(4):
            frame = self._tx(CMD_RW, bytes([ACTION_READ]))
            if (
                frame[0] == REPLY_RW
                and len(frame) >= 5 + STATUS_LEN + 1
                and frame[4] == ACTION_STATUS
            ):
                return parse_status(frame[5 : 5 + STATUS_LEN])
        raise ProtocolError("no status frame received")

    def _write(self, mask: int, *, w: int = 0, n0: int = 3, n6: int = 0) -> PurifierState:
        self._tx(CMD_RW, write_payload(mask, w=w, n0=n0, n6=n6))
        time.sleep(self._settle)
        return self._read_state()

    def get_state(self) -> PurifierState:
        return self._call(self._read_state)

    def set_power(self, on: bool) -> PurifierState:
        def op() -> PurifierState:
            n0 = MODE_IDS.get(self._read_state().mode or "auto", 3)
            if on:
                return self._write(MASK_POWER | MASK_MODE, w=1, n0=n0)
            return self._write(MASK_POWER, w=0, n0=n0)

        return self._call(op)

    def set_mode(self, mode: str) -> PurifierState:
        return self._call(lambda: self._write(MASK_MODE, n0=MODE_IDS[mode]))

    def set_light(self, light: str) -> PurifierState:
        return self._call(lambda: self._write(MASK_LIGHT, n6=LIGHT_IDS[light]))


# --------------------------------------------------------------------------- discovery
def format_mac(mac: bytes | bytearray) -> str:
    return ":".join(f"{b:02x}" for b in mac)


@dataclass(frozen=True)
class FoundDevice:
    host: str
    mac: str


def probe(host: str, *, timeout: float = 2.0, hello: Callable[..., Any] | None = None) -> FoundDevice | None:
    """Return the device if ``host`` is a supported purifier, otherwise None."""
    if hello is None:
        import broadlink  # noqa: PLC0415

        hello = broadlink.hello
    try:
        dev = hello(host, timeout=timeout)
    except Exception:  # noqa: BLE001 - no answer, host without Broadlink, etc.
        return None
    if getattr(dev, "devtype", None) != DEVTYPE:
        return None
    return FoundDevice(host=host, mac=format_mac(dev.mac))


def scan(
    networks: Iterable[ipaddress.IPv4Network],
    *,
    timeout: float = 1.0,
    workers: int = 48,
    hello: Callable[..., Any] | None = None,
) -> list[FoundDevice]:
    """Look for purifiers in the given networks with a unicast hello to every address."""
    hosts: list[str] = []
    for net in networks:
        if net.num_addresses > 1024:  # huge networks are not swept
            continue
        hosts.extend(str(ip) for ip in net.hosts())
    found: list[FoundDevice] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for item in pool.map(lambda h: probe(h, timeout=timeout, hello=hello), hosts):
            if item is not None and item not in found:
                found.append(item)
    return found
