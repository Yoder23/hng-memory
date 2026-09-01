"""Read-only Windows handle-type snapshots for bounded diagnostics."""

from __future__ import annotations

from collections import Counter
import ctypes
from ctypes import wintypes
import os
from typing import Final


SYSTEM_EXTENDED_HANDLE_INFORMATION: Final = 64
OBJECT_TYPE_INFORMATION: Final = 2
STATUS_INFO_LENGTH_MISMATCH: Final = 0xC0000004


class SystemHandleEntryEx(ctypes.Structure):
    _fields_ = [
        ("object", ctypes.c_void_p),
        ("process_id", ctypes.c_size_t),
        ("handle_value", ctypes.c_size_t),
        ("granted_access", wintypes.DWORD),
        ("creator_backtrace_index", wintypes.WORD),
        ("object_type_index", wintypes.WORD),
        ("handle_attributes", wintypes.DWORD),
        ("reserved", wintypes.DWORD),
    ]


def _unsigned_status(status: int) -> int:
    return ctypes.c_ulong(status).value


def current_process_handle_types() -> Counter[str]:
    """Return a type-name histogram for handles owned by this process."""
    if os.name != "nt":
        raise RuntimeError("Windows is required for handle-type snapshots")
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtQuerySystemInformation.restype = wintypes.LONG
    ntdll.NtQueryObject.restype = wintypes.LONG

    size = 1 << 20
    while True:
        buffer = ctypes.create_string_buffer(size)
        required = wintypes.ULONG()
        status = ntdll.NtQuerySystemInformation(
            SYSTEM_EXTENDED_HANDLE_INFORMATION,
            buffer,
            size,
            ctypes.byref(required),
        )
        if status == 0:
            break
        if _unsigned_status(status) != STATUS_INFO_LENGTH_MISMATCH:
            raise OSError(
                f"NtQuerySystemInformation failed: "
                f"0x{_unsigned_status(status):08x}"
            )
        size = max(size * 2, int(required.value))

    word = ctypes.sizeof(ctypes.c_size_t)
    count = ctypes.c_size_t.from_buffer_copy(buffer.raw[:word]).value
    offset = word * 2
    entries = (SystemHandleEntryEx * count).from_buffer(buffer, offset)
    histogram: Counter[str] = Counter()
    process_id = os.getpid()
    for entry in entries:
        if entry.process_id != process_id:
            continue
        type_buffer = ctypes.create_string_buffer(4096)
        required = wintypes.ULONG()
        status = ntdll.NtQueryObject(
            ctypes.c_void_p(entry.handle_value),
            OBJECT_TYPE_INFORMATION,
            type_buffer,
            len(type_buffer),
            ctypes.byref(required),
        )
        if status != 0:
            histogram["<query-error>"] += 1
            continue
        length = ctypes.c_ushort.from_buffer_copy(type_buffer.raw[:2]).value
        pointer = ctypes.c_void_p.from_buffer_copy(type_buffer.raw[8:16]).value
        name = ctypes.wstring_at(pointer, length // 2) if pointer and length else ""
        histogram[name or "<unnamed>"] += 1
    return histogram


if __name__ == "__main__":
    import json

    print(json.dumps(current_process_handle_types(), sort_keys=True))
