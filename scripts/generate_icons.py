#!/usr/bin/env python3
"""Generate PNG icons and OG social preview image from the brand palette."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "webapp" / "static" / "icons"

BG = (0x1A, 0x3A, 0x2A, 0xFF)
BG_DARK = (0x12, 0x14, 0x0E, 0xFF)
BG_MID = (0x1A, 0x1D, 0x13, 0xFF)
BORDER = (0x3A, 0x40, 0x28, 0xFF)
AMBER = (0xFF, 0xB6, 0x48, 0xFF)
KHAKI = (0xCD, 0xC2, 0x94, 0xFF)
OLIVE = (0x8A, 0x9A, 0x5B, 0xFF)
GREEN = (0x9A, 0xCD, 0x68, 0xFF)
DIM = (0x8F, 0x8C, 0x77, 0xFF)

RAYS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _write_rgba_png(path: Path, width: int, height: int, pixels: list[bytes]) -> None:
    rows = [b"\x00" + row for row in pixels]
    raw = b"".join(rows)
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", ihdr)
    png += _png_chunk(b"IDAT", compressed)
    png += _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def _sun_color(
    x: float, y: float, cx: float, cy: float, size: float, bg: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    dx = x - cx
    dy = y - cy
    dist = (dx * dx + dy * dy) ** 0.5
    core_r = size * 0.17
    ray_inner = size * 0.24
    ray_outer = size * 0.44
    if dist <= core_r:
        return AMBER
    for ux, uy in RAYS:
        denom = ux * ux + uy * uy
        t = (dx * ux + dy * uy) / denom if denom else 0
        if t < ray_inner or t > ray_outer:
            continue
        perp = abs(dx * uy - dy * ux) / (denom ** 0.5)
        if perp <= max(1.2, size * 0.025):
            return AMBER
    return bg


def _fill_rect(
    pixels: list[bytearray],
    x0: int, y0: int, x1: int, y1: int,
    color: tuple[int, int, int, int],
    width: int,
) -> None:
    for y in range(max(0, y0), min(len(pixels), y1)):
        row = pixels[y]
        for x in range(max(0, x0), min(width, x1)):
            i = x * 4
            row[i : i + 4] = bytes(color)


def _draw_hline(pixels: list[bytearray], y: int, x0: int, x1: int, color: tuple[int, int, int, int]) -> None:
    if 0 <= y < len(pixels):
        row = pixels[y]
        for x in range(x0, x1):
            if 0 <= x * 4 < len(row):
                i = x * 4
                row[i : i + 4] = bytes(color)


def _glyph(char: str) -> list[str]:
    font: dict[str, list[str]] = {
        "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
        "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
        "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
        "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
        "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
        "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
        "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
        "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
        "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
        "M": ["10001", "11011", "10101", "10001", "10001", "10001", "10001"],
        "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
        "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
        "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
        "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
        "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
        "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
        "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
        "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
        "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
        "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
        " ": ["00000"] * 7,
        "·": ["00000", "00000", "00100", "00000", "00100", "00000", "00000"],
        "→": ["00000", "00100", "00010", "11111", "00010", "00100", "00000"],
    }
    return font.get(char, font[" "])


def _blit_char(
    pixels: list[bytearray],
    x: int, y: int,
    char: str,
    scale: int,
    color: tuple[int, int, int, int],
    width: int,
) -> int:
    glyph = _glyph(char)
    for gy, row in enumerate(glyph):
        for gx, bit in enumerate(row):
            if bit != "1":
                continue
            for dy in range(scale):
                for dx in range(scale):
                    px, py = x + gx * scale + dx, y + gy * scale + dy
                    if 0 <= py < len(pixels) and 0 <= px < width:
                        i = px * 4
                        pixels[py][i : i + 4] = bytes(color)
    return len(glyph[0]) * scale + scale


def _blit_text(
    pixels: list[bytearray],
    x: int, y: int,
    text: str,
    scale: int,
    color: tuple[int, int, int, int],
    width: int,
) -> None:
    cursor = x
    for char in text:
        cursor += _blit_char(pixels, cursor, y, char, scale, color, width)


def write_icon_png(path: Path, size: int) -> None:
    cx = cy = (size - 1) / 2
    pixels = []
    for y in range(size):
        row = bytearray(size * 4)
        for x in range(size):
            color = _sun_color(x, y, cx, cy, size, BG)
            i = x * 4
            row[i : i + 4] = color
        pixels.append(bytes(row))
    _write_rgba_png(path, size, size, pixels)


def write_og_image(path: Path, width: int = 1200, height: int = 630) -> None:
    pixels = [bytearray(width * 4) for _ in range(height)]
    for y in range(height):
        t = y / max(height - 1, 1)
        bg = tuple(int(BG_DARK[i] + (BG_MID[i] - BG_DARK[i]) * t) for i in range(3)) + (255,)
        for x in range(width):
            i = x * 4
            pixels[y][i : i + 4] = bytes(bg)

    _fill_rect(pixels, 48, 48, width - 48, height - 48, BORDER, width)
    _draw_hline(pixels, 49, 49, width - 49, BORDER)
    _draw_hline(pixels, height - 50, 49, width - 49, BORDER)

    sun_size = 220.0
    cx, cy = 180.0, height / 2
    for y in range(height):
        for x in range(width):
            color = _sun_color(x, y, cx, cy, sun_size, (0, 0, 0, 0))
            if color[3] and color != (0, 0, 0, 0):
                i = x * 4
                pixels[y][i : i + 4] = bytes(color)

    _blit_text(pixels, 280, 200, "COH UCS TOOLS", 6, KHAKI, width)
    _blit_text(pixels, 280, 290, "LOCALIZATION COMMAND CONSOLE", 3, DIM, width)
    _blit_text(pixels, 280, 370, "ANALYZE · COMPARE · MERGE · VALIDATE", 3, GREEN, width)
    _blit_text(pixels, 280, 430, "UTF-16-LE · FF FE BOM · CRLF · ID→TEXT", 3, OLIVE, width)

    _write_rgba_png(path, width, height, [bytes(r) for r in pixels])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        write_icon_png(OUT / name, size)
        print(f"Wrote {OUT / name} ({size}x{size})")
    write_og_image(OUT / "og-image.png")
    print(f"Wrote {OUT / 'og-image.png'} (1200x630)")


if __name__ == "__main__":
    main()
