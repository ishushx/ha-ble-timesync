"""Protocol frames reconstructed from the WeChat mini program wx890d0ddb0174a600.

All values below come from the unpacked app-service.js / utils/util.js.
No BCD, no encryption, no signature. Time fields use *local* time.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .const import (
    MODEL_GENERAL,
    MODEL_LED,
    MODEL_MJL,
    MODEL_QINGZHOU,
    MODEL_WST,
    SERVICE_UUIDS,
)


def _weekday(dt: datetime) -> int:
    """Mirror JavaScript getDay(): Sunday=0 ... Saturday=6."""
    return dt.isoweekday() % 7


def frame_general(dt: datetime) -> bytes:
    """timeToBytes: 6 bytes, no year."""
    hour, minute, second = dt.hour, dt.minute, dt.second
    return bytes((0xFC, (hour + minute + second) & 0xFF, hour, minute, second, 0xFC))


def frame_led(dt: datetime) -> bytes:
    """timeToBytes2: 10 bytes, year offset 2000."""
    year = dt.year - 2000
    month, day = dt.month, dt.day
    weekday = _weekday(dt)
    return bytes(
        (
            0xFC,
            (year + month + day) & 0xFF,
            year,
            month,
            day,
            weekday,
            dt.hour,
            dt.minute,
            dt.second,
            0xFC,
        )
    )


def frame_qingzhou(dt: datetime) -> bytes:
    """timeToBytes3: 14 bytes, year offset 1792, checksum 0xD9."""
    year = dt.year - 1792
    month = dt.month
    weekday = _weekday(dt)
    day = dt.day
    hour, minute, second = dt.hour, dt.minute, dt.second
    checksum = (0xD9 + year + month + weekday + day + hour + minute + second) & 0xFF
    return bytes(
        (
            0x55,
            0x01,
            0x0B,
            0x71,
            0x07,
            year,
            month,
            weekday,
            day,
            hour,
            minute,
            second,
            checksum,
            0xAA,
        )
    )


def frame_mjl(dt: datetime) -> bytes:
    """timeToBytes4: 8 bytes, no header/footer, no checksum."""
    year = dt.year - 2000
    return bytes(
        (
            (year + dt.month + dt.day) & 0xFF,
            year,
            dt.month,
            dt.day,
            _weekday(dt),
            dt.hour,
            dt.minute,
            dt.second,
        )
    )


def frame_wst(dt: datetime) -> bytes:
    """timeToBytes5: 9 bytes, checksum 0xDD."""
    hour, minute, second = dt.hour, dt.minute, dt.second
    checksum = (0xDD + hour + minute + second) & 0xFF
    return bytes((0xA5, 0x02, 0x05, 0x05, 0xD1, hour, minute, second, checksum))


FRAME_BUILDERS: dict[str, Callable[[datetime], bytes]] = {
    MODEL_GENERAL: frame_general,
    MODEL_LED: frame_led,
    MODEL_QINGZHOU: frame_qingzhou,
    MODEL_MJL: frame_mjl,
    MODEL_WST: frame_wst,
}


def build_payload(model: str, when: datetime) -> bytes:
    """Build the exact bytes written by the mini program."""
    if model not in FRAME_BUILDERS:
        raise ValueError(f"Unsupported model: {model}")

    frame = FRAME_BUILDERS[model](when)
    if model == MODEL_MJL:
        # 源码: new Uint8Array("*" + ab2hext(frame) + "*"), 小写 hex。
        return b"*" + frame.hex().encode("ascii") + b"*"
    # 源码: value.slice(0, 20)。所有非 MJL 帧都 <= 14 B，因此等价。
    return frame[:20]


def _short_uuid(value: str) -> str:
    """Normalize a 128-bit UUID to its 16-bit short form."""
    uuid = str(value).lower()
    if uuid.startswith("0000") and uuid.endswith("-0000-1000-8000-00805f9b34fb"):
        return uuid[4:8]
    return uuid


def detect_service_family(service_uuid: str | None) -> str | None:
    """Return ff00/ffe0/9900/fff0, or None."""
    if not service_uuid:
        return None
    short = _short_uuid(service_uuid)
    for family, full_uuid in SERVICE_UUIDS.items():
        if short == _short_uuid(full_uuid):
            return family
    return None


def guess_model(family: str | None, name: str | None) -> str | None:
    """Mirror the routing logic in pages/index/index.js L1192."""
    device_name = (name or "").strip()
    if family == "ff00":
        return MODEL_GENERAL if device_name in {"YHD-MODULE", "JM_Cabinet"} else MODEL_LED
    if family == "ffe0":
        return MODEL_MJL if device_name == "JM_Cabinet" else MODEL_LED
    if family == "9900":
        return MODEL_QINGZHOU if device_name in {"JM_Cabinet", "BXICHENG"} else MODEL_LED
    if family == "fff0":
        return MODEL_WST
    return None
