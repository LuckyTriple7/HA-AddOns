#!/usr/bin/env python3
"""Generates the add-on icons as flat PNGs, pure stdlib (zlib only).

No image library is installed in this environment, so the icon is built by
hand: a rounded-square accent background with a simple three-node "network"
glyph in white, computed per pixel. Run once; the output is committed.
"""

import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BG = (9, 105, 218)      # --accent (light theme value reads well at small sizes)
FG = (255, 255, 255)

# Node centres and the lines between them, in unit coordinates (0..1).
NODES = [(0.27, 0.74), (0.73, 0.74), (0.5, 0.26)]
EDGES = [(0, 1), (0, 2), (1, 2)]


def _round_rect_mask(x, y, size, radius):
    cx, cy = size / 2, size / 2
    half = size / 2 - 1
    dx, dy = abs(x - cx) - (half - radius), abs(y - cy) - (half - radius)
    if dx <= 0 or dy <= 0:
        return True
    return (dx * dx + dy * dy) <= radius * radius


def _dist_to_segment(px, py, ax, ay, bx, by):
    abx, aby = bx - ax, by - ay
    length2 = abx * abx + aby * aby
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / length2))
    ex, ey = ax + t * abx, ay + t * aby
    return ((px - ex) ** 2 + (py - ey) ** 2) ** 0.5


def render(size: int) -> bytes:
    node_r = size * 0.085
    line_w = size * 0.035
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            if not _round_rect_mask(x, y, size, size * 0.18):
                row += bytes((0, 0, 0, 0))
                continue
            u, v = x / size, y / size
            on_glyph = False
            for ax, ay in NODES:
                if (u - ax) ** 2 + (v - ay) ** 2 <= (node_r / size) ** 2:
                    on_glyph = True
                    break
            if not on_glyph:
                for a, b in EDGES:
                    ax, ay = NODES[a]
                    bx, by = NODES[b]
                    d = _dist_to_segment(u, v, ax, ay, bx, by) * size
                    if d <= line_w:
                        on_glyph = True
                        break
            color = FG if on_glyph else BG
            row += bytes(color) + bytes((255,))
        rows.append(bytes(row))
    return b''.join(b'\x00' + r for r in rows)


def write_png(path: Path, size: int) -> None:
    raw = render(size)
    ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data)))

    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    path.write_bytes(png)
    print(f'wrote {path} ({size}x{size}, {len(png)} bytes)')


if __name__ == '__main__':
    write_png(HERE / 'icon.png', 128)
    write_png(HERE / 'icon-192.png', 192)
    write_png(HERE / 'icon-512.png', 512)
    write_png(HERE / 'static' / 'icon-192.png', 192)
    write_png(HERE / 'static' / 'icon-512.png', 512)
