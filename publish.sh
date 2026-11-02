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
#    Push HEAD rather than the local "main" branch: a pre-provisioned checkout can be a
#    detached HEAD whose local "main" is stale, and pushing that stale branch is rejected.
cd "$REPO_DIR"
git add "editions/$DATE.json"
git "${GIT_ID[@]}" commit -q -m "Edition $DATE" || true
pushed=
for i in 1 2 3; do
  if git "${GIT_ID[@]}" pull -q --rebase origin main && git push -q origin HEAD:main; then
    pushed=1; break
  fi
  sleep 5
done
if [ -z "$pushed" ]; then
  echo "site published, but pushing editions/$DATE.json to main failed 3 times" >&2
  exit 1
fi
# Keep the local main branch in step with what was pushed.
[ "$(git symbolic-ref -q --short HEAD || true)" = main ] || git branch -f main HEAD
echo "published $DATE"
