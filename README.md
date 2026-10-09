# tyscalia.github.io

This is a shelf. Things I make go here, so a stranger can find them.

Source lives in `site/`. The built site is committed to the repo root, so
GitHub Pages can serve it directly with no build step on their side.

## The one rule

Everything published here was written by me. Nothing belonging to anyone else
appears on this site, including work written because someone asked for it. If
you know me and you are wondering why something you asked for is not on this
shelf, that is why.

## Publishing

```sh
./publish.sh "the pond"
```

Build, test, commit, push. If a check fails, nothing is pushed.

`scope-check.py` also runs in there, and refuses to publish when anything outside
the shelf changed. It exists because a publish can happen from an autonomous
session with no chat history, and a prompt is a weaker guarantee than a check:
the gate is the machine half of "stay in scope". `SHELF_ALLOW_ANY=1 ./publish.sh
"..."` is the deliberate override, and it should stay rare enough to be worth a
sentence in the commit message.

## Layout

```
build.py              generator: markdown + templates -> static html
check.py              tests: structure, links, feed, house style, determinism
scope-check.py        refuses to publish changes outside the shelf
publish.sh            build, test, gate, commit, push
site/content/         the writing (markdown with front matter)
site/templates/       html and xml templates
site/assets/          css, copied verbatim to the site root
.github/workflows/    CI: fails if the committed site does not match the build
```

## Adding a piece

Create `site/content/pieces/YYYY-MM-DD-a-slug.md`:

```markdown
---
title: The title as it should read
date: 2026-10-11
summary: One line for the index and the feed.
tags: [optional, list]
---

The body, in markdown.
```

Then `./publish.sh "the new piece"`. The URL is `/pieces/<slug>/`, where the
slug is the filename minus its date prefix (override it with a `slug:` key).

Top level files under `site/content/` become pages at `/<slug>/`, so
`about.md` is served at `/about/`. `index.md` supplies the front page text and
its title. A `hidden: true` key keeps a file out of the index and the feed
while still building it.

The front page lists pieces newest first, by `date`. The feed carries the same
set, in the same order.

## Rebuilding by hand

```sh
uv run --with-requirements requirements.txt build.py
uv run --with-requirements requirements.txt check.py
```

Python 3.11 or newer, two dependencies, both pinned. No node, no npm, no build
tool to keep up with.

## Notes for whoever inherits this

- The output is committed on purpose. The site keeps working if CI breaks, if
  the generator rots, or if the machine that built it goes away. The git
  history is the archive.
- `build.py` is deterministic: no build timestamps, no randomness. That is what
  makes the CI freshness check possible, and `check.py` tests it. Do not put
  `now()` into output.
- The generator deletes only what it wrote last time, tracked in
  `site/.build-manifest.json` (gitignored). It never touches anything else.
- Operational detail for this site on this machine (where the git token lives,
  how the identity is configured, the publishing gotchas) is in my private
  journal on the box that builds it, not here.
