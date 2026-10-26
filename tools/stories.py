#!/usr/bin/env python3
"""List stories from the BBC snapshot in front-page order, de-duplicated by URL.

    python3 tools/stories.py            # top 14 as JSON, plus snapshot age on stderr
    python3 tools/stories.py --max-age-hours 12   # exit 2 if the snapshot is older
"""
import argparse
import datetime as dt
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent


def canonical(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=14)
    ap.add_argument("--max-age-hours", type=float)
    a = ap.parse_args()

    snap = (ROOT / "data" / "snapshot-time.txt").read_text().strip()
    taken = dt.datetime.fromisoformat(snap.replace("Z", "+00:00"))
    age = (dt.datetime.now(dt.timezone.utc) - taken).total_seconds() / 3600
    print(f"snapshot taken {snap} ({age:.1f} h ago)", file=sys.stderr)
    if a.max_age_hours is not None and age > a.max_age_hours:
        print(f"STALE: older than {a.max_age_hours} h", file=sys.stderr)
        return 2

    root = ET.parse(ROOT / "data" / "bbc-top-stories.xml").getroot()
    seen, out = set(), []
    for item in root.findall("./channel/item"):
        link = canonical(item.findtext("link", ""))
        if not link or link in seen:
            continue
        seen.add(link)
        out.append({"title": item.findtext("title", "").strip(),
                    "description": item.findtext("description", "").strip(),
                    "link": link,
                    "pubDate": item.findtext("pubDate", "")})
        if len(out) >= a.n:
            break
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
