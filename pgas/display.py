"""Frames for the UNO Q 8x13 LED matrix.

The matrix is driven by the MCU. Python renders a frame here (104 brightness
values, 0-7, row-major) and sends it over the Bridge; the sketch's "draw"
handler copies it into the buffer it shows with matrix.draw().
"""

from __future__ import annotations

ROWS, COLS = 8, 13
ON = 7

# 3x5 glyphs, each row a 3-bit mask (MSB = left column).
FONT = {
    "0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7), "2": (7, 1, 7, 4, 7), "3": (7, 1, 7, 1, 7),
    "4": (5, 5, 7, 1, 1), "5": (7, 4, 7, 1, 7), "6": (7, 4, 7, 5, 7), "7": (7, 1, 2, 2, 2),
    "8": (7, 5, 7, 5, 7), "9": (7, 5, 7, 1, 7),
    "A": (2, 5, 7, 5, 5),  # ambient baseline
    "H": (5, 5, 7, 5, 5),  # hood over the food
    "V": (5, 5, 5, 5, 2),  # vent / recover
    "C": (7, 4, 4, 4, 7),  # continuous logging
    "M": (5, 7, 7, 5, 5),  # move the hood now
    "T": (7, 2, 2, 2, 2),  # self-test
    "E": (7, 4, 6, 4, 7),  # error
    " ": (0, 0, 0, 0, 0),
}

_ICONS = {
    "FRESH": (  # check mark
        "0000000000000",
        "0000000000011",
        "0000000000110",
        "0000000001100",
        "0110000011000",
        "0011000110000",
        "0001101100000",
        "0000111000000",
    ),
    "SPOILING": (  # exclamation mark in a box
        "1111111111111",
        "1000001000001",
        "1000001000001",
        "1000001000001",
        "1000001000001",
        "1000000000001",
        "1000001000001",
        "1111111111111",
    ),
    "DO-NOT-SELL": (  # cross
        "0011000001100",
        "0001100011000",
        "0000110110000",
        "0000011100000",
        "0000011100000",
        "0000110110000",
        "0001100011000",
        "0011000001100",
    ),
}


def blank() -> list[int]:
    return [0] * (ROWS * COLS)


def _put_glyph(frame: list[int], ch: str, col: int, row: int = 0, level: int = ON) -> None:
    for r, bits in enumerate(FONT[ch]):
        for c in range(3):
            if bits & (4 >> c):
                x, y = col + c, row + r
                if 0 <= x < COLS and 0 <= y < ROWS:
                    frame[y * COLS + x] = level


def text3(chars: str, row: int = 0) -> list[int]:
    """Up to 3 glyphs at columns 0, 5 and 9 (letter, gap, two digits)."""
    f = blank()
    for ch, col in zip(chars, (0, 5, 9)):
        _put_glyph(f, ch, col, row)
    return f


def countdown(letter: str, seconds_left: int, progress: float) -> list[int]:
    """Phase letter + 2-digit countdown on rows 0-4, progress bar on row 7."""
    s = max(0, min(99, int(seconds_left)))
    f = text3(f"{letter}{s // 10}{s % 10}")
    filled = round(max(0.0, min(1.0, progress)) * COLS)
    for x in range(filled):
        f[7 * COLS + x] = ON
    return f


def icon(grade: str) -> list[int]:
    rows = _ICONS[grade]
    return [ON if ch == "1" else 0 for row in rows for ch in row]


def to_bytes(frame: list[int]) -> bytes:
    if len(frame) != ROWS * COLS:
        raise ValueError("frame must have 104 pixels")
    return bytes(max(0, min(ON, int(v))) for v in frame)


def ascii_art(frame: list[int]) -> str:
    return "\n".join("".join("#" if frame[y * COLS + x] else "." for x in range(COLS)) for y in range(ROWS))
