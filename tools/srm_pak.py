#!/usr/bin/env python3
"""
Move a Controller Pak between a RetroArch .srm and this recompilation's save.

RetroArch's mupen64plus core stores every save type a cartridge might use in
one .srm, concatenated in a fixed order:

    0x00000  0x00800   EEPROM
    0x00800  0x20000   Controller Pak, 4 x 0x8000, one per port
    0x20800  0x08000   SRAM
    0x28800  0x20000   FlashRAM
                       -------
    0x48800            total

Goemon's Great Adventure saves to the Controller Pak in port 1, so the 0x8000
bytes at 0x800 are the whole save. The runtime keeps its save buffer in
`saves/<game_id>.bin`, sized by the game's SaveType; GGA declares AllowAll,
which is 0x20000, and `src/game/joybus.cpp` maps the pak to the front of it.
So importing is a copy from one offset to another, and the rest of the runtime
buffer stays zero because GGA uses no other save type.

A pak image is self-describing enough to check rather than trust: the ID block
at 0x20 is repeated at 0x60, 0x80 and 0xC0, and its last four bytes are a
checksum over the preceding 28. Both conventions for the inverted half are
seen in the wild (`-sum` and `0xFFF2 - sum`), so both are accepted.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

SRM_SIZE = 0x48800
PAK_OFFSET = 0x800
PAK_SIZE = 0x8000
RUNTIME_SAVE_SIZE = 0x20000
ID_COPIES = (0x20, 0x60, 0x80, 0xC0)


def id_checksums(block: bytes) -> tuple[int, int]:
    """The stored checksum pair for a 32 byte ID block."""
    return struct.unpack(">HH", block[28:32])


def computed_checksum(block: bytes) -> int:
    words = struct.unpack(">14H", block[:28])
    return sum(words) & 0xFFFF


def check_pak(pak: bytes) -> list[str]:
    """Return a list of problems; empty means the image looks valid."""
    problems = []
    if len(pak) != PAK_SIZE:
        problems.append(f"pak is {len(pak)} bytes, expected {PAK_SIZE}")
        return problems

    primary = pak[ID_COPIES[0]:ID_COPIES[0] + 32]
    for off in ID_COPIES[1:]:
        if pak[off:off + 32] != primary:
            problems.append(f"ID block copy at 0x{off:02X} differs from 0x20")

    stored_sum, stored_inv = id_checksums(primary)
    want = computed_checksum(primary)
    if stored_sum != want:
        problems.append(f"ID checksum is 0x{stored_sum:04X}, computed 0x{want:04X}")
    # Both inverted-checksum conventions are in circulation.
    if stored_inv not in ((-want) & 0xFFFF, (0xFFF2 - want) & 0xFFFF):
        problems.append(
            f"inverted checksum 0x{stored_inv:04X} matches neither "
            f"0x{(-want) & 0xFFFF:04X} nor 0x{(0xFFF2 - want) & 0xFFFF:04X}"
        )
    return problems


def extract_note_data(pak: bytes, entry: int = 0) -> bytes:
    """The contents of one note, following its page chain.

    A pak is 128 pages of 256 bytes. Page 0 holds the ID blocks, pages 1 and 2
    the inode table and its backup, pages 3 and 4 the note table, and the rest
    is data. A note records only its first page; the inode table gives the next
    page of each, ending at 1.

    This is needed because a game whose osPfs* calls the runtime intercepts
    never sees the pak at all -- osPfsReadWriteFile is answered straight out of
    the save buffer, so that buffer holds the note's contents rather than an
    image of the pak around it.
    """
    note = pak[0x300 + entry * 32:0x300 + entry * 32 + 32]
    start_page = int.from_bytes(note[6:8], "big")
    out = bytearray()
    page = start_page
    seen = set()
    while 5 <= page < 128 and page not in seen:
        seen.add(page)
        out += pak[page * 256:(page + 1) * 256]
        page = int.from_bytes(pak[0x100 + page * 2:0x100 + page * 2 + 2], "big")
    return bytes(out)


def notes(pak: bytes) -> list[str]:
    """Names of the occupied note-table entries, for identifying a pak."""
    # N64 note names use their own character set; only the ranges needed to
    # make a name readable are mapped, and anything else is shown as '?'.
    charset = {0: " ", 15: " "}
    for i in range(10):
        charset[16 + i] = chr(ord("0") + i)
    for i in range(26):
        charset[26 + i] = chr(ord("A") + i)

    out = []
    for entry in range(16):
        off = 0x300 + entry * 32
        note = pak[off:off + 32]
        game_code = note[0:4]
        if game_code == b"\x00\x00\x00\x00" or game_code == b"\xff\xff\xff\xff":
            continue
        name = "".join(charset.get(c, "?") for c in note[16:32]).rstrip()
        printable = "".join(chr(c) if 32 <= c < 127 else "." for c in game_code)
        out.append(f"{printable} {name}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("direction", choices=("import", "export", "import-note"),
                    help="import: .srm -> runtime save (raw pak, for a game that "
                         "talks to the pak itself); export: runtime save -> .srm; "
                         "import-note: .srm -> runtime save holding only the "
                         "note's contents, for a game whose osPfs* calls the "
                         "runtime answers")
    ap.add_argument("--srm", type=Path, required=True, help="RetroArch .srm")
    ap.add_argument("--save", type=Path, required=True, help="runtime saves/<game_id>.bin")
    ap.add_argument("--port", type=int, default=1, choices=(1, 2, 3, 4),
                    help="controller port whose pak to use (default: 1)")
    ap.add_argument("--force", action="store_true",
                    help="proceed even if the pak image fails its checks")
    args = ap.parse_args()

    pak_at = PAK_OFFSET + (args.port - 1) * PAK_SIZE

    if args.direction == "import-note":
        srm = args.srm.read_bytes()
        if len(srm) != SRM_SIZE:
            print(f"error: {args.srm} is {len(srm)} bytes, expected {SRM_SIZE}",
                  file=sys.stderr)
            return 1
        pak = srm[pak_at:pak_at + PAK_SIZE]
        for p in check_pak(pak):
            print(f"warning: {p}", file=sys.stderr)
        found = notes(pak)
        if not found:
            print("error: no notes in that pak", file=sys.stderr)
            return 1
        print(f"note: {found[0]}")
        data = extract_note_data(pak)
        print(f"note contents: {len(data)} bytes")

        buf = bytearray(RUNTIME_SAVE_SIZE)
        if args.save.exists():
            existing = args.save.read_bytes()
            buf[:len(existing)] = existing[:RUNTIME_SAVE_SIZE]
        buf[0:len(data)] = data
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_bytes(bytes(buf))
        print(f"wrote {args.save} ({len(buf)} bytes), note contents at offset 0")
        return 0

    if args.direction == "import":
        srm = args.srm.read_bytes()
        if len(srm) != SRM_SIZE:
            print(f"error: {args.srm} is {len(srm)} bytes, expected {SRM_SIZE}; "
                  "this does not look like a RetroArch mupen64plus .srm",
                  file=sys.stderr)
            return 1

        pak = srm[pak_at:pak_at + PAK_SIZE]
        problems = check_pak(pak)
        if problems:
            for p in problems:
                print(f"warning: {p}", file=sys.stderr)
            if not args.force:
                print("refusing to import; pass --force to override", file=sys.stderr)
                return 1

        found = notes(pak)
        print(f"pak in port {args.port}: {len(found)} note(s)")
        for n in found:
            print(f"  {n}")

        # Preserve anything already in the rest of the runtime buffer.
        if args.save.exists():
            buf = bytearray(args.save.read_bytes().ljust(RUNTIME_SAVE_SIZE, b"\x00"))
            del buf[RUNTIME_SAVE_SIZE:]
        else:
            buf = bytearray(RUNTIME_SAVE_SIZE)
        buf[0:PAK_SIZE] = pak

        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_bytes(bytes(buf))
        print(f"wrote {args.save} ({len(buf)} bytes), pak at offset 0")
    else:
        save = args.save.read_bytes()
        if len(save) < PAK_SIZE:
            print(f"error: {args.save} is only {len(save)} bytes", file=sys.stderr)
            return 1
        pak = save[:PAK_SIZE]
        for p in check_pak(pak):
            print(f"warning: {p}", file=sys.stderr)

        srm = bytearray(args.srm.read_bytes()) if args.srm.exists() else bytearray(SRM_SIZE)
        if len(srm) != SRM_SIZE:
            print(f"error: {args.srm} is {len(srm)} bytes, expected {SRM_SIZE}",
                  file=sys.stderr)
            return 1
        srm[pak_at:pak_at + PAK_SIZE] = pak
        args.srm.write_bytes(bytes(srm))
        print(f"wrote pak into {args.srm} at 0x{pak_at:X}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
