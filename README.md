# CW Headlines

The day's top ten news stories, summarized and sent in Morse code. There are five podcasts, one per speed:

| Feed | Speed |
|---|---|
| `https://slester.github.io/cw-news/feeds/10wpm.xml` | 10 WPM, Farnsworth (characters at 20 WPM) |
| `https://slester.github.io/cw-news/feeds/15wpm.xml` | 15 WPM, Farnsworth (characters at 20 WPM) |
| `https://slester.github.io/cw-news/feeds/20wpm.xml` | 20 WPM |
| `https://slester.github.io/cw-news/feeds/25wpm.xml` | 25 WPM |
| `https://slester.github.io/cw-news/feeds/30wpm.xml` | 30 WPM |

## How a daily edition is made

1. **04:30 Paris** (05:30 in summer): the `Snapshot BBC top stories` GitHub Action saves
   `https://feeds.bbci.co.uk/news/rss.xml` to `data/bbc-top-stories.xml`.
2. **06:36 Paris**: a Claude scheduled task reads that snapshot. It takes the first ten distinct
   stories in BBC's front-page order and writes `editions/YYYY-MM-DD.json`: one 15–25 word summary
   per story, in its own words and limited to characters Morse code can send.
3. Claude runs `build.py`. The script renders each edition at the five speeds (600 Hz, 5 ms
   raised-cosine keying, a -60 dBFS noise floor, 32 kbps mono MP3) and rewrites the five feeds.
   The noise floor is there because the Apple Podcasts app clicks whenever the audio drops to
   exact digital silence, which plain CW does between every element. It also prunes audio older
   than 14 days.
4. The site goes to the `gh-pages` branch as a single fresh commit each day, so the repo doesn't grow.
   GitHub Pages serves it, and podcast apps pick up the new episodes.

Each transmission is sent like this:

```
VVV VVV <BT> CW HEADLINES 27 OCT 2026 <BT> NR 1 ... <BT> NR 2 ... <BT> ... NR 10 ... <AR>
```

The episode notes show exactly what is sent, one line per story with the time it starts in that episode and a link to the story, so you can check what you copied.

## Files

- `morse.py`: the text-to-CW renderer (PARIS timing, Farnsworth spacing)
- `build.py`: turns editions into MP3s, feeds and the landing page (`--check` only validates)
- `art.py`: generates the covers in `art/` (3000 px for Apple, 600 px embedded in the MP3s)
- `tools/decode_check.py`: decodes a rendered MP3 back to text and measures dits and gaps
- `config.json`: show title, author, speeds, tone, noise floor, retention. Changing any audio
  setting re-renders the retained episodes on the next build. Set `owner_email` if you want a
  contact email in the feeds (it is public).

## Run it yourself

```sh
pip install numpy pillow        # plus ffmpeg with libmp3lame
git worktree add ../site gh-pages
python3 build.py --site ../site
```

## Not affiliated with the BBC

Stories are picked from the BBC's public top-stories feed and summarized independently. No BBC text
or branding is used.
