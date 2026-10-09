#!/usr/bin/env python3
"""Tests for the shelf. Run after build.py; exits non-zero on any failure.

    uv run --with-requirements requirements.txt check.py

What it checks, and why each one earns its place:

  structure   every content file has a page on disk, with the right <title>, and
              its own prose in the output (catches a template that drops {{body}},
              and a build that silently produced nothing)
  index       every published piece is listed and linked on the front page
  links       every internal href/src in the generated html resolves to a file
              (catches renamed slugs, broken nav, missing stylesheet)
  feed        feed.xml parses as XML, one entry per piece, links match, dated
  style       no em dashes or en dashes anywhere in the output. House rule.
  determinism building twice produces byte-identical files. This is what makes
              the CI freshness check meaningful, so it is a test, not a nicety.
"""

from __future__ import annotations

import hashlib
import html.parser
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import build

FAILURES: list[str] = []
TAGS = re.compile(r"<[^>]+>")
ATOM = {"a": "http://www.w3.org/2005/Atom"}


def check(condition: bool, message: str) -> bool:
    """Record a failure. Returns the condition so callers can branch on it."""
    if not condition:
        FAILURES.append(message)
    return condition


class Page(html.parser.HTMLParser):
    """A generated document: its refs, its <title>, its visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[str] = []
        self.text: list[str] = []
        self.title = ""
        self._in_title = False
        self._muted = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"style", "script"}:
            self._muted += 1
        if tag == "title":
            self._in_title = True
        for key, value in attrs:
            if key in {"href", "src"} and value:
                self.refs.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"style", "script"} and self._muted:
            self._muted -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
        elif not self._muted and data.strip():
            self.text.append(data.strip())


def parse(path: Path) -> Page:
    page = Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def visible_text(path: Path) -> str:
    return " ".join(parse(path).text)


def prose_of(doc: build.Doc) -> str:
    """First ~12 words of the rendered body, tags stripped, whitespace collapsed."""
    words = " ".join(TAGS.sub(" ", doc.body_html).split()).split()
    return " ".join(words[:12])


def fingerprint(paths: list[Path]) -> str:
    sha = hashlib.sha256()
    for path in sorted(paths):
        sha.update(str(path.relative_to(build.ROOT)).encode())
        sha.update(path.read_bytes())
    return sha.hexdigest()


def resolve(ref: str, page: Path) -> Path:
    """Where does an internal ref point on disk?"""
    if ref.startswith("/"):
        target = build.ROOT / ref.lstrip("/")
    else:
        target = page.parent / ref
    if ref.endswith("/"):
        target = target / "index.html"
    return target.resolve()


def main() -> int:
    print("building...")
    subprocess.run([sys.executable, "build.py", "--quiet"], cwd=build.ROOT, check=True)

    docs = build.load_docs()
    index = next(d for d in docs if d.kind == "index")
    pages = [d for d in docs if d.kind == "page" and not d.hidden]
    pieces = [d for d in docs if d.kind == "piece" and not d.hidden]
    manifest = build.owned_paths()
    every = [index, *pages, *pieces]

    # structure ------------------------------------------------------------
    for doc in every:
        if not check(doc.out_path.exists(), f"no output for {doc.url}"):
            continue
        page = parse(doc.out_path)
        if doc.kind != "index":
            check(
                page.title.startswith(doc.title),
                f"{doc.url}: <title> is {page.title!r}, expected {doc.title!r} first",
            )
        needle = prose_of(doc)
        check(
            needle in visible_text(doc.out_path),
            f"{doc.url}: body prose missing from the rendered page ({needle[:40]!r}...)",
        )

    # index ----------------------------------------------------------------
    if index.out_path.exists():
        index_html = index.out_path.read_text(encoding="utf-8")
        index_text = visible_text(index.out_path)
        for piece in pieces:
            check(piece.title in index_text, f"index does not name {piece.title!r}")
            check(piece.url in index_html, f"index does not link to {piece.url}")

    # links ----------------------------------------------------------------
    for doc in every:
        if not doc.out_path.exists():
            continue
        for ref in parse(doc.out_path).refs:
            if ref.startswith(("http://", "https://", "mailto:", "#")):
                continue
            check(
                resolve(ref, doc.out_path).exists(),
                f"{doc.url}: broken link {ref}",
            )

    # feed -----------------------------------------------------------------
    feed_path = build.ROOT / "feed.xml"
    if check(feed_path.exists(), "feed.xml missing"):
        root = ET.fromstring(feed_path.read_text(encoding="utf-8"))
        entries = root.findall("a:entry", ATOM)
        check(
            len(entries) == len(pieces),
            f"feed has {len(entries)} entries for {len(pieces)} pieces",
        )
        links = {e.find("a:link", ATOM).get("href") for e in entries}  # type: ignore[union-attr]
        check(
            links == {build.SITE_URL + p.url for p in pieces},
            "feed entry links do not match the piece urls",
        )
        updated = root.find("a:updated", ATOM)
        check(updated is not None and bool(updated.text), "feed has no <updated>")

    # style ----------------------------------------------------------------
    for path in manifest:
        if path.suffix in {".html", ".xml", ".css"}:
            text = path.read_text(encoding="utf-8")
            check("\u2014" not in text, f"{path.name}: em dash")
            check("\u2013" not in text, f"{path.name}: en dash")

    # determinism ----------------------------------------------------------
    before = fingerprint(manifest)
    subprocess.run([sys.executable, "build.py", "--quiet"], cwd=build.ROOT, check=True)
    check(before == fingerprint(build.owned_paths()), "build is not deterministic")

    if FAILURES:
        print(f"\nFAIL ({len(FAILURES)})")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"ok: {len(manifest)} files, {len(pieces)} piece(s), {len(pages)} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
