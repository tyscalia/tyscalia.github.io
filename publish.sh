#!/usr/bin/env bash
# Build, test, commit, push. This is the only supported way to publish:
# the checks run before anything leaves the machine, and the built html is
# committed with the source that produced it.
#
#   ./publish.sh "the pond"
set -euo pipefail
cd "$(dirname "$0")"

message="${1:-publish}"
uv run --with-requirements requirements.txt build.py
uv run --with-requirements requirements.txt check.py
python3 scope-check.py

git add -A
if git diff --cached --quiet; then
  echo "nothing to publish"
  exit 0
fi

git commit -q -m "$message"
git push -q origin main
echo "pushed: $(git log -1 --format='%h %s')"
