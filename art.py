#!/usr/bin/env python3
"""Generate cover art: art/<wpm>wpm.jpg (3000 px, for Apple) and art/<wpm>wpm-600.jpg (embedded in MP3s)."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from morse import CODE

ROOT = Path(__file__).resolve().parent
FONTS = Path("/usr/share/fonts/opentype/inter")
BG_TOP, BG_BOTTOM = (15, 26, 36), (22, 37, 51)
CREAM, AMBER, MUTED = (243, 235, 221), (242, 163, 58), (159, 176, 191)
S = 3000
M = 220  # outer margin


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def tracked(draw, xy, text, fnt, fill, tracking):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill, anchor="ls")
        x += draw.textlength(ch, font=fnt) + tracking
    return x


def morse_bars(draw, text, x0, y0, max_w, max_unit=70):
    symbols = [CODE[c] for c in text]
    units = sum(sum(1 if e == "." else 3 for e in s) + (len(s) - 1) for s in symbols) + 3 * (len(symbols) - 1)
    u = min(max_unit, max_w // units)
    x = x0
    for si, s in enumerate(symbols):
        for ei, e in enumerate(s):
            w = u if e == "." else 3 * u
            draw.rounded_rectangle((x, y0, x + w, y0 + u), radius=u // 2, fill=AMBER)
            x += w + (u if ei < len(s) - 1 else 0)
        x += 3 * u if si < len(symbols) - 1 else 0
    return u


def cover(speed: dict, title: str) -> Image.Image:
    t = np.linspace(0, 1, S)[:, None, None]
    grad = np.array(BG_TOP) + (np.array(BG_BOTTOM) - np.array(BG_TOP)) * t
    img = Image.fromarray(np.broadcast_to(grad, (S, S, 3)).round().astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    wpm = str(speed["wpm"])

    morse_bars(d, wpm, M, 330, S - 2 * M)

    unit_font = font("InterDisplay-Bold.otf", 300)
    room = S - 2 * M + 40 - 70 - d.textlength("WPM", font=unit_font)
    size = 1550
    while d.textlength(wpm, font=font("InterDisplay-Black.otf", size)) > room:
        size -= 10
    big = font("InterDisplay-Black.otf", size)
    baseline = 2020
    d.text((M - 40, baseline), wpm, font=big, fill=CREAM, anchor="ls")
    num_w = d.textlength(wpm, font=big)
    d.text((M - 40 + num_w + 70, baseline), "WPM", font=unit_font, fill=AMBER, anchor="ls")
    if speed.get("farnsworth_char_wpm"):
        note = font("Inter-SemiBold.otf", 96)
        d.text((M - 40 + num_w + 80, baseline - 380), "FARNSWORTH", font=note, fill=MUTED, anchor="ls")
        d.text((M - 40 + num_w + 80, baseline - 260),
               f"{speed['farnsworth_char_wpm']} WPM CHARS", font=note, fill=MUTED, anchor="ls")

    d.line((M, 2300, S - M, 2300), fill=(52, 70, 86), width=8)
    tracked(d, (M, 2580), title.upper(), font("InterDisplay-Bold.otf", 250), CREAM, 18)
    tracked(d, (M, 2760), "DAILY NEWS IN MORSE CODE", font("Inter-SemiBold.otf", 112), MUTED, 10)
    return img


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    out = ROOT / "art"
    out.mkdir(exist_ok=True)
    for sp in cfg["speeds"]:
        img = cover(sp, cfg["show_title"])
        img.save(out / f"{sp['wpm']}wpm.jpg", quality=88, optimize=True, progressive=True)
        img.resize((600, 600), Image.LANCZOS).save(out / f"{sp['wpm']}wpm-600.jpg", quality=85)
        print("art", sp["wpm"])


if __name__ == "__main__":
    main()
