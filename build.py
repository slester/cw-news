#!/usr/bin/env python3
"""Render editions/*.json into Morse MP3s and five podcast feeds.

Usage:
    python3 build.py --site ../site            # render what's missing, rewrite feeds
    python3 build.py --site ../site --check    # validate editions only, render nothing

The site directory is the checkout of the gh-pages branch that GitHub Pages serves.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import morse

ROOT = Path(__file__).resolve().parent
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def load_json(path: Path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def slug(speed: dict) -> str:
    return f"{speed['wpm']}wpm"


def speed_label(speed: dict) -> str:
    if speed.get("farnsworth_char_wpm"):
        return f"{speed['wpm']} WPM (Farnsworth, {speed['farnsworth_char_wpm']} WPM characters)"
    return f"{speed['wpm']} WPM"


def transmission(ed: dict) -> str:
    d = dt.date.fromisoformat(ed["date"])
    header = f"VVV VVV <BT> CW HEADLINES {d.day} {MONTHS[d.month - 1]} {d.year} <BT>"
    body = " <BT> ".join(f"NR {i} {s['text']}" for i, s in enumerate(ed["stories"], 1))
    return f"{header} {body} <AR>"


def validate(ed: dict, name: str) -> list[str]:
    problems = []
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ed.get("date", "")):
        problems.append(f"{name}: missing or bad 'date'")
    stories = ed.get("stories", [])
    if len(stories) != 10:
        problems.append(f"{name}: expected 10 stories, found {len(stories)}")
    for i, s in enumerate(stories, 1):
        text = s.get("text", "")
        words = len(text.split())
        if not 8 <= words <= 40:
            problems.append(f"{name} NR {i}: {words} words (keep it to 8-40)")
        _, dropped = morse.normalise(text)
        if dropped:
            problems.append(f"{name} NR {i}: characters with no Morse code: {''.join(sorted(dropped))!r}")
        if "<" in text or ">" in text:
            problems.append(f"{name} NR {i}: angle brackets are reserved for prosigns")
    return problems


def pub_datetime(ed: dict, cfg: dict) -> dt.datetime:
    if ed.get("published"):
        return dt.datetime.fromisoformat(ed["published"])
    hh, mm = map(int, cfg["publish_time"].split(":"))
    return dt.datetime.combine(dt.date.fromisoformat(ed["date"]), dt.time(hh, mm),
                               tzinfo=ZoneInfo(cfg["timezone"]))


def show_notes(ed: dict, speed: dict) -> str:
    items = []
    for i, s in enumerate(ed["stories"], 1):
        copy, _ = morse.normalise(s["text"])
        link = f' <a href="{html.escape(s["link"])}">Story</a>' if s.get("link") else ""
        items.append(f"<li>NR {i} {html.escape(copy)}{link}</li>")
    return (
        f"<p>Today's ten stories in Morse code at {html.escape(speed_label(speed))}. "
        "Copy along, then check yourself against the text below.</p>"
        f"<ol>{''.join(items)}</ol>"
        "<p>Stories are picked from the BBC News top-stories feed and summarized "
        "independently. This podcast is not affiliated with the BBC.</p>"
    )


def channel_description(cfg: dict, speed: dict) -> str:
    return (
        f"{cfg['tagline']}, at {speed_label(speed)}. A new edition every morning: ten short "
        "summaries of the top stories on the BBC News front page, sent as clean 600 Hz CW. "
        "The full plain-text copy is in each episode's notes so you can check what you copied. "
        "Not affiliated with the BBC."
    )


def write_feed(cfg: dict, speed: dict, episodes: list[dict], site: Path) -> Path:
    base = cfg["base_url"].rstrip("/")
    s = slug(speed)
    feed_url = f"{base}/feeds/{s}.xml"
    title = f"{cfg['show_title']} · {speed['wpm']} WPM"
    now = format_datetime(dt.datetime.now(dt.timezone.utc))
    owner = ""
    if cfg.get("owner_email"):
        owner = (f"<itunes:owner><itunes:name>{html.escape(cfg['author'])}</itunes:name>"
                 f"<itunes:email>{html.escape(cfg['owner_email'])}</itunes:email></itunes:owner>")
    items = []
    for ep in episodes:
        d = dt.date.fromisoformat(ep["date"])
        items.append(f"""
    <item>
      <title>{d.day} {d.strftime('%b %Y')} · {speed['wpm']} WPM</title>
      <guid isPermaLink="false">cw-headlines-{ep['date']}-{s}</guid>
      <pubDate>{format_datetime(ep['pub'])}</pubDate>
      <enclosure url="{base}/audio/{ep['file']}" length="{ep['bytes']}" type="audio/mpeg"/>
      <itunes:duration>{round(ep['duration'])}</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>
      <description><![CDATA[{ep['notes']}]]></description>
      <content:encoded><![CDATA[{ep['notes']}]]></content:encoded>
    </item>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{html.escape(title)}</title>
    <link>{base}/</link>
    <atom:link href="{feed_url}" rel="self" type="application/rss+xml"/>
    <language>{cfg['language']}</language>
    <description>{html.escape(channel_description(cfg, speed))}</description>
    <itunes:summary>{html.escape(channel_description(cfg, speed))}</itunes:summary>
    <itunes:author>{html.escape(cfg['author'])}</itunes:author>
    {owner}
    <itunes:image href="{base}/art/{s}.jpg"/>
    <itunes:category text="Leisure"><itunes:category text="Hobbies"/></itunes:category>
    <itunes:category text="News"><itunes:category text="Daily News"/></itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <lastBuildDate>{now}</lastBuildDate>{''.join(items)}
  </channel>
</rss>
"""
    out = site / "feeds" / f"{s}.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(xml, encoding="utf-8")
    return out


def write_index(cfg: dict, site: Path, latest: str | None) -> None:
    base = cfg["base_url"].rstrip("/")
    rows = "".join(
        f'<li><img src="art/{slug(sp)}.jpg" alt="" width="72" height="72">'
        f'<div><strong>{sp["wpm"]} WPM</strong><span>{html.escape(speed_label(sp))}</span>'
        f'<code>{base}/feeds/{slug(sp)}.xml</code></div></li>'
        for sp in cfg["speeds"])
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(cfg['show_title'])}</title>
<style>
:root{{--bg:#0f1a24;--fg:#f3ebdd;--muted:#9fb0bf;--accent:#f2a33a;--card:#162533}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:680px;margin:0 auto;padding:40px 16px}}
h1{{margin:0 0 4px;font-size:32px;letter-spacing:.04em}}
p{{color:var(--muted)}}
ul{{list-style:none;padding:0;display:grid;gap:12px}}
li{{display:flex;gap:14px;align-items:center;background:var(--card);border-radius:10px;padding:12px}}
li img{{border-radius:6px;flex:none}}
li div{{display:flex;flex-direction:column;min-width:0}}
li span{{color:var(--muted);font-size:14px}}
code{{color:var(--accent);font-size:13px;overflow-wrap:anywhere}}
</style></head><body><main>
<h1>{html.escape(cfg['show_title'])}</h1>
<p>{html.escape(cfg['tagline'])}. One feed per speed — subscribe in any podcast app with the URL.
{f'Latest edition: {latest}.' if latest else ''}</p>
<ul>{rows}</ul>
<p>Stories are picked from the BBC News top-stories feed and summarized independently. Not affiliated with the BBC.</p>
</main></body></html>
"""
    (site / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, type=Path)
    ap.add_argument("--check", action="store_true", help="validate editions and exit")
    ap.add_argument("--force", action="store_true", help="re-render every retained episode")
    ap.add_argument("--editions", type=Path, default=ROOT / "editions", help=argparse.SUPPRESS)
    args = ap.parse_args()

    cfg = load_json(ROOT / "config.json")
    editions = []
    problems = []
    for path in sorted(args.editions.glob("*.json")):
        ed = load_json(path)
        problems += validate(ed, path.name)
        editions.append(ed)
    if problems:
        print("Edition problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    if not editions:
        print("No editions found.", file=sys.stderr)
        return 1
    if args.check:
        print(f"{len(editions)} edition(s) OK")
        return 0

    newest = max(dt.date.fromisoformat(e["date"]) for e in editions)
    cutoff = newest - dt.timedelta(days=cfg["retention_days"] - 1)
    kept = sorted((e for e in editions if dt.date.fromisoformat(e["date"]) >= cutoff),
                  key=lambda e: e["date"], reverse=True)

    site = args.site
    (site / "audio").mkdir(parents=True, exist_ok=True)
    (site / "art").mkdir(parents=True, exist_ok=True)
    (site / ".nojekyll").touch()
    for art in (ROOT / "art").glob("*.jpg"):
        shutil.copy2(art, site / "art" / art.name)

    index_path = site / "episodes.json"
    index = load_json(index_path, {})
    wanted = set()
    for ed in kept:
        text = transmission(ed)
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        for sp in cfg["speeds"]:
            name = f"{ed['date']}-{slug(sp)}.mp3"
            wanted.add(name)
            meta = index.get(name)
            out = site / "audio" / name
            if args.force or not out.exists() or not meta or meta.get("hash") != digest:
                timing = morse.timing_for(sp["wpm"], sp.get("farnsworth_char_wpm"))
                d = dt.date.fromisoformat(ed["date"])
                duration = morse.render_mp3(
                    text, timing, str(out), sr=cfg["sample_rate"], bitrate=cfg["bitrate"],
                    freq=cfg["tone_hz"], cover=str(ROOT / "art" / f"{slug(sp)}-600.jpg"),
                    tags={"title": f"{d.day} {d.strftime('%b %Y')} · {sp['wpm']} WPM",
                          "artist": cfg["author"],
                          "album": f"{cfg['show_title']} · {sp['wpm']} WPM",
                          "date": ed["date"], "genre": "Podcast"})
                index[name] = {"duration": duration, "bytes": out.stat().st_size, "hash": digest}
                print(f"rendered {name}  {duration / 60:5.1f} min  {out.stat().st_size / 1e6:4.1f} MB")

    for f in (site / "audio").glob("*.mp3"):
        if f.name not in wanted:
            f.unlink()
            index.pop(f.name, None)
            print(f"pruned {f.name}")
    index = {k: v for k, v in index.items() if k in wanted}
    index_path.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")

    for sp in cfg["speeds"]:
        eps = []
        for ed in kept:
            name = f"{ed['date']}-{slug(sp)}.mp3"
            eps.append({"date": ed["date"], "file": name, "pub": pub_datetime(ed, cfg),
                        "duration": index[name]["duration"], "bytes": index[name]["bytes"],
                        "notes": show_notes(ed, sp)})
        print(f"wrote {write_feed(cfg, sp, eps, site).relative_to(site)} ({len(eps)} episodes)")
    write_index(cfg, site, kept[0]["date"] if kept else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
