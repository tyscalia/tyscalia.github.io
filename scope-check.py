#!/usr/bin/env python3
"""Scope gate. Refuses to publish a change that touches files outside the shelf.

    python3 scope-check.py [--quiet]

Why this exists: publishing runs happen inside autonomous, context-free sessions
(see HOUR.md). A prompt can say "do not touch anything else" and a cold session
can still wander; this is the machine-checkable half of that instruction. The
generator's own output and its tests are the only things allowed to change.

Exit 0 = the working tree is in scope. Exit 1 = list the offenders, change nothing.

Bypass deliberately, with the reason in the commit message:

    SHELF_ALLOW_ANY=1 ./publish.sh "..."
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parent

# Everything the generator writes, plus the small set of files that make it work.
ALLOWED_EXACT = {
    ".gitignore",
    "404.html",
    "README.md",
    "build.py",
    "check.py",
    "feed.xml",
    "index.html",
    "publish.sh",
    "requirements.txt",
    "robots.txt",
    "scope-check.py",
    "sitemap.xml",
    "style.css",
}
ALLOWED_DIRS = (
    "site/",  # the source: content, templates, assets
    "pieces/",  # generated: pieces/<slug>/index.html
    "about/",
    "now/",
)
ALLOWED_WORKFLOWS = (".github/workflows/check.yml",)


def changed_paths() -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    paths = []
    for line in out.splitlines():
        entry = line[3:].strip().strip('"')
        if " -> " in entry:  # renames: check both sides
            paths.extend(part.strip() for part in entry.split(" -> "))
        else:
            paths.append(entry)
    return sorted(set(paths))


def in_scope(path: str) -> bool:
    if path in ALLOWED_EXACT or path in ALLOWED_WORKFLOWS:
        return True
    return any(path.startswith(prefix) for prefix in ALLOWED_DIRS)


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    if os.environ.get("SHELF_ALLOW_ANY") == "1":
        if not quiet:
            print("scope: bypassed (SHELF_ALLOW_ANY=1)")
        return 0

    offenders = [p for p in changed_paths() if not in_scope(p)]
    if offenders:
        print("scope: REFUSING to publish, files outside the shelf changed:")
        for path in offenders:
            print(f"  - {path}")
        print("Move scratch work to /opt/data/cache/scratch, or bypass with")
        print("SHELF_ALLOW_ANY=1 if the change really is the point.")
        return 1

    if not quiet:
        print("scope: ok (nothing outside the shelf touched)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
