#!/usr/bin/env python3
"""Apple Podcasts channel artwork.

art/channel-icon.png  3000x3000, no transparency, shown cropped to a circle
art/channel-logo.png  3000x750, transparent, horizontal, sits on the channel background colour (#0F1A24)
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from art import AMBER, BG_BOTTOM, BG_TOP, CREAM, font, morse_bars

ROOT = Path(__file__).resolve().parent


def icon():
    s = 3000
    t = np.linspace(0, 1, s)[:, None, None]
    grad = np.array(BG_TOP) + (np.array(BG_BOTTOM) - np.array(BG_TOP)) * t
    img = Image.fromarray(np.broadcast_to(grad, (s, s, 3)).round().astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    big = font("InterDisplay-Black.otf", 1050)
    d.text((s / 2, 1756), "CW", font=big, fill=CREAM, anchor="ms")
    # "CW" in Morse, centred under the letters, kept well inside the circle.
    probe = Image.new("RGB", (s, 200))
    u = morse_bars(ImageDraw.Draw(probe), "CW", 0, 0, 1500, max_unit=95)
    units = (3 + 1 + 1 + 1 + 3 + 1 + 1) + 3 + (1 + 1 + 3 + 1 + 3)  # -.-.  .--
    morse_bars(d, "CW", round((s - units * u) / 2), 1956, 1500, max_unit=95)
    img.save(ROOT / "art" / "channel-icon.png", optimize=True)


def logo():
    w, h = 3000, 750
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 520
    while True:
        f = font("InterDisplay-Bold.otf", size)
        gap = size * 0.28
        total = d.textlength("CW", font=f) + gap + d.textlength("HEADLINES", font=f)
        if total <= 2760:
            break
        size -= 5
    x = (w - total) / 2
    base = h / 2 + size * 0.36
    d.text((x, base), "CW", font=f, fill=AMBER + (255,), anchor="ls")
    d.text((x + d.textlength("CW", font=f) + gap, base), "HEADLINES", font=f, fill=CREAM + (255,), anchor="ls")
    img.save(ROOT / "art" / "channel-logo.png", optimize=True)


if __name__ == "__main__":
    icon()
    logo()
