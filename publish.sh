#!/usr/bin/env bash
# Build the site from editions/ and publish it to the gh-pages branch as one fresh commit.
# Usage: ./publish.sh YYYY-MM-DD      (run from the repo root, after writing editions/YYYY-MM-DD.json)
set -euo pipefail

DATE="${1:?usage: publish.sh YYYY-MM-DD}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE="${SITE:-$REPO_DIR/../cw-news-site}"
REMOTE="$(git -C "$REPO_DIR" remote get-url origin)"
GIT_ID=(-c user.name="CW Headlines bot" -c user.email="noreply@anthropic.com")

test -f "$REPO_DIR/editions/$DATE.json" || { echo "missing editions/$DATE.json" >&2; exit 1; }
python3 "$REPO_DIR/build.py" --site /dev/null --check

# 1. Get the current site (keeps the last 14 days of audio so it isn't re-rendered).
rm -rf "$SITE"
if git -C "$REPO_DIR" ls-remote --exit-code origin refs/heads/gh-pages >/dev/null 2>&1; then
  git clone -q --depth 1 --branch gh-pages "$REMOTE" "$SITE"
else
  git init -q -b gh-pages "$SITE"
  git -C "$SITE" remote add origin "$REMOTE"
fi

# 2. Render new audio, prune old audio, rewrite feeds.
python3 "$REPO_DIR/build.py" --site "$SITE"

# 3. Publish the site as a single orphan commit so the branch never accumulates old MP3s.
cd "$SITE"
git checkout -q --orphan publish
git add -A
git "${GIT_ID[@]}" commit -q -m "Edition $DATE"
git push -q --force origin publish:gh-pages

# 4. Record the edition on main.
cd "$REPO_DIR"
git add "editions/$DATE.json"
git "${GIT_ID[@]}" commit -q -m "Edition $DATE" || true
for i in 1 2 3; do
  git pull -q --rebase origin main && git push -q origin main && break
  sleep 5
done
echo "published $DATE"
