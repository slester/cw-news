"""Morse (CW) text-to-audio renderer.

Timing follows the PARIS standard: one unit = 1.2 / wpm seconds.
When an effective speed lower than the character speed is given, the
Farnsworth method (ARRL, Bloom KE3Z) stretches only the gaps between
characters and words, so letters keep the sound of the faster speed.

A faint noise floor can be mixed under the whole transmission. The Apple
Podcasts app clicks every time the audio falls to exact digital silence (the
same file plays cleanly from the Files app), so the gaps between elements must
never be true zeros. At -60 dBFS the noise survives 32 kbps MP3 encoding
(about -63 dBFS RMS after decoding) and sits ~60 dB under the tone.
"""
from __future__ import annotations

import math
import re
import subprocess
import unicodedata
from dataclasses import dataclass

import numpy as np

CODE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", '"': ".-..-.",
    "@": ".--.-.",
}

# Prosigns are written <XX> in the text and sent as one run-together character.
PROSIGN_RE = re.compile(r"<([A-Z]{2,3})>")

_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "%": " PERCENT",
    "£": " POUNDS ", "€": " EUROS ", "$": " DOLLARS ",
}


def normalise(text: str) -> tuple[str, set[str]]:
    """Upper-case, strip accents, map common symbols; return (text, dropped chars)."""
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    out, dropped = [], set()
    i = 0
    while i < len(text):
        m = PROSIGN_RE.match(text, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        ch = text[i]
        if ch in CODE or ch == " ":
            out.append(ch)
        elif ch in "\n\t":
            out.append(" ")
        else:
            dropped.add(ch)
        i += 1
    return re.sub(r" {2,}", " ", "".join(out)).strip(), dropped


def tokenize(text: str) -> list[list[str]]:
    """Split normalised text into words, each a list of element strings ('.-')."""
    words = []
    for word in text.split(" "):
        chars, i = [], 0
        while i < len(word):
            m = PROSIGN_RE.match(word, i)
            if m:
                chars.append("".join(CODE[c] for c in m.group(1)))
                i = m.end()
            else:
                chars.append(CODE[word[i]])
                i += 1
        if chars:
            words.append(chars)
    return words


@dataclass(frozen=True)
class Timing:
    char_wpm: float
    eff_wpm: float

    @property
    def unit(self) -> float:
        return 1.2 / self.char_wpm

    @property
    def char_gap(self) -> float:
        if self.eff_wpm >= self.char_wpm:
            return 3 * self.unit
        ta = (60 * self.char_wpm - 37.2 * self.eff_wpm) / (self.eff_wpm * self.char_wpm)
        return 3 * ta / 19

    @property
    def word_gap(self) -> float:
        if self.eff_wpm >= self.char_wpm:
            return 7 * self.unit
        ta = (60 * self.char_wpm - 37.2 * self.eff_wpm) / (self.eff_wpm * self.char_wpm)
        return 7 * ta / 19


def timing_for(wpm: int, farnsworth_char_wpm: int | None = None) -> Timing:
    if farnsworth_char_wpm and farnsworth_char_wpm > wpm:
        return Timing(char_wpm=farnsworth_char_wpm, eff_wpm=wpm)
    return Timing(char_wpm=wpm, eff_wpm=wpm)


def _tone(seconds: float, sr: int, freq: float, amp: float, ramp: float) -> np.ndarray:
    n = int(round(seconds * sr))
    t = np.arange(n) / sr
    wave = np.sin(2 * math.pi * freq * t)
    r = min(int(round(ramp * sr)), n // 2)
    if r:
        env = 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, r))
        wave[:r] *= env
        wave[-r:] *= env[::-1]
    return (wave * amp * 32767).astype(np.int16)


def _silence(seconds: float, sr: int) -> np.ndarray:
    return np.zeros(int(round(seconds * sr)), dtype=np.int16)


def _noise_mixer(noise_dbfs: float | None):
    """Return a function that adds white noise at `noise_dbfs` (RMS) to an int16 chunk."""
    if noise_dbfs is None:
        return lambda chunk: chunk
    rng = np.random.default_rng(0)  # fixed seed: the same edition always renders identically
    scale = 32767 * 10 ** (noise_dbfs / 20)

    def mix(chunk: np.ndarray) -> np.ndarray:
        noise = np.round(rng.standard_normal(len(chunk)) * scale).astype(np.int32)
        return np.clip(chunk.astype(np.int32) + noise, -32768, 32767).astype(np.int16)
    return mix


def render_pcm(text: str | list[str], timing: Timing, *, sr: int = 32000, freq: float = 600.0,
               amp: float = 0.7, ramp: float = 0.005, lead_in: float = 1.0,
               tail: float = 2.0, marks: list | None = None, noise_dbfs: float | None = None):
    """Yield int16 PCM chunks (one per word).

    `text` may be a list of lines; they are sent as if joined with spaces. If `marks`
    is given, the start time in seconds of each line is appended to it. If `noise_dbfs`
    is given, white noise at that RMS level runs under the whole transmission.
    """
    mix = _noise_mixer(noise_dbfs)
    lines = [text] if isinstance(text, str) else list(text)
    words, owner = [], []
    for li, line in enumerate(lines):
        for w in tokenize(normalise(line)[0]):
            words.append(w)
            owner.append(li)
    u = timing.unit
    dit, dah = _tone(u, sr, freq, amp, ramp), _tone(3 * u, sr, freq, amp, ramp)
    gap_el, gap_ch, gap_wd = _silence(u, sr), _silence(timing.char_gap, sr), _silence(timing.word_gap, sr)
    lead = _silence(lead_in, sr)
    pos = len(lead)
    yield mix(lead)
    for wi, word in enumerate(words):
        if marks is not None and (wi == 0 or owner[wi] != owner[wi - 1]):
            marks.append(pos / sr)
        parts = []
        for ci, ch in enumerate(word):
            for ei, el in enumerate(ch):
                parts.append(dit if el == "." else dah)
                if ei < len(ch) - 1:
                    parts.append(gap_el)
            if ci < len(word) - 1:
                parts.append(gap_ch)
        if wi < len(words) - 1:
            parts.append(gap_wd)
        chunk = np.concatenate(parts)
        pos += len(chunk)
        yield mix(chunk)
    yield mix(_silence(tail, sr))


def render_mp3(text: str | list[str], timing: Timing, out_path: str, *, sr: int = 32000,
               bitrate: str = "32k", freq: float = 600.0, tags: dict | None = None,
               cover: str | None = None, marks: list | None = None,
               noise_dbfs: float | None = None) -> float:
    """Encode the transmission to MP3. Returns duration in seconds; fills `marks` (see render_pcm)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-"]
    if cover:
        cmd += ["-i", cover, "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg",
                "-disposition:v", "attached_pic"]
    cmd += ["-c:a", "libmp3lame", "-b:a", bitrate, "-ar", str(sr), "-ac", "1",
            "-id3v2_version", "3"]
    for k, v in (tags or {}).items():
        cmd += ["-metadata", f"{k}={v}"]
    cmd.append(out_path)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    samples = 0
    for chunk in render_pcm(text, timing, sr=sr, freq=freq, marks=marks, noise_dbfs=noise_dbfs):
        samples += len(chunk)
        proc.stdin.write(chunk.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out_path}")
    return samples / sr
