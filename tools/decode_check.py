#!/usr/bin/env python3
"""Decode a rendered MP3 back to text and measure its timing.

    python3 tools/decode_check.py audio.mp3 --wpm 10 --char-wpm 20 --expect "TEXT"

Exits non-zero if the decoded copy differs from the expected text or the
measured effective speed is more than 2% off.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import morse  # noqa: E402

REVERSE = {v: k for k, v in morse.CODE.items()}
PROSIGNS = {"-...-": "=", ".-.-.": "+"}  # BT and AR share codes with = and +
SR = 32000


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "s16le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def segments(x):
    env = np.convolve(np.abs(x), np.ones(int(SR * 0.004)) / int(SR * 0.004), mode="same")
    on = env > 0.2 * env.max()
    edges = np.flatnonzero(np.diff(on.astype(np.int8)))
    bounds = np.concatenate(([0], edges + 1, [len(on)]))
    return [(bool(on[a]), (b - a) / SR) for a, b in zip(bounds[:-1], bounds[1:])]


def decode(segs, unit):
    words, chars, cur = [], [], ""
    for is_on, dur in segs:
        if is_on:
            cur += "." if dur < 2 * unit else "-"
        elif cur:
            if dur < 2 * unit:
                continue
            chars.append(cur)
            cur = ""
            if dur > 5 * unit:
                words.append(chars)
                chars = []
    if cur:
        chars.append(cur)
    if chars:
        words.append(chars)
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp3")
    ap.add_argument("--wpm", type=float, required=True)
    ap.add_argument("--char-wpm", type=float)
    ap.add_argument("--expect", required=True)
    a = ap.parse_args()
    timing = morse.timing_for(int(a.wpm), int(a.char_wpm) if a.char_wpm else None)
    segs = segments(pcm(a.mp3))
    # Interior segments only: drop the lead-in and tail silence.
    body = segs[1:-1] if not segs[0][0] else segs
    if body and not body[-1][0]:
        body = body[:-1]
    # Classify gaps against Farnsworth spacing: char gaps vs word gaps use the stretched values.
    gap_char_word_split = (timing.char_gap + timing.word_gap) / 2
    words, chars, cur = [], [], ""
    for is_on, dur in body:
        if is_on:
            cur += "." if dur < 2 * timing.unit else "-"
            continue
        if dur < (timing.unit + timing.char_gap) / 2:
            continue
        chars.append(cur)
        cur = ""
        if dur > gap_char_word_split:
            words.append(chars)
            chars = []
    chars.append(cur)
    words.append(chars)

    expected = morse.tokenize(morse.normalise(a.expect)[0])
    ok_text = words == expected
    if not ok_text:
        for i, (got, want) in enumerate(zip(words, expected)):
            if got != want:
                print(f"first mismatch at word {i}: got {got} want {want}")
                break
        print(f"words decoded {len(words)} vs expected {len(expected)}")

    ons = [d for o, d in body if o]
    dits = [d for d in ons if d < 2 * timing.unit]
    dahs = [d for d in ons if d >= 2 * timing.unit]
    # Effective speed: PARIS units in the expected text over the measured body duration.
    units = 0
    for wi, w in enumerate(expected):
        for ci, c in enumerate(w):
            units += sum(1 if e == "." else 3 for e in c) + (len(c) - 1)
            if ci < len(w) - 1:
                units += 3
        if wi < len(expected) - 1:
            units += 7
    span = sum(d for _, d in body)
    eff = 1.2 * units / span
    offs = [d for o, d in body if not o]
    split_el = (timing.unit + timing.char_gap) / 2
    char_gaps = [d for d in offs if split_el <= d <= gap_char_word_split]
    word_gaps = [d for d in offs if d > gap_char_word_split]
    # The envelope threshold trims ~2 ms off each tone's ramps and adds it to the gaps.
    def close(measured, want):
        return abs(measured - want) <= max(0.03 * want, 0.006)
    checks = {
        "dit": close(np.median(dits), timing.unit),
        "letter gap": close(np.median(char_gaps), timing.char_gap),
        "word gap": close(np.median(word_gaps), timing.word_gap),
    }
    # The PARIS reference word must take exactly 60 / wpm seconds with these gaps.
    paris = 31 * timing.unit + 4 * timing.char_gap + timing.word_gap
    checks["PARIS"] = abs(paris - 60 / a.wpm) < 1e-9
    ok_speed = all(checks.values())
    print(f"{Path(a.mp3).name}: copy {'OK' if ok_text else 'MISMATCH'} | "
          f"dit {np.median(dits) * 1000:.0f}/{timing.unit * 1000:.0f} ms | "
          f"letter gap {np.median(char_gaps) * 1000:.0f}/{timing.char_gap * 1000:.0f} ms | "
          f"word gap {np.median(word_gaps) * 1000:.0f}/{timing.word_gap * 1000:.0f} ms | "
          f"PARIS {paris:.3f}s | text rate {eff:.2f} WPM | "
          f"{'timing OK' if ok_speed else 'TIMING OFF: ' + ', '.join(k for k, v in checks.items() if not v)}")
    return 0 if ok_text and ok_speed else 1


if __name__ == "__main__":
    sys.exit(main())
