#!/usr/bin/env python3
"""Generator for tyscalia.github.io.

    markdown + templates in site/  ->  static html committed to the repo root

Why committed output: GitHub Pages serves the files in this repo directly, so
the site keeps working if CI, the build tool, or the machine that built it
disappears. History is the archive.

Contract, in order of how much it matters:

1. Deterministic. No build timestamps, no randomness, no dict-order luck.
   check.py builds twice and compares hashes; CI diffs the committed output
   against a fresh build. Introducing `now()` into output breaks both.
2. It owns only what it generates. Every path written is recorded in
   site/.build-manifest.json (gitignored); the next build deletes exactly those
   paths first. Nothing else in the repo is ever removed.
3. Two dependencies, both pinned in requirements.txt.

Usage:
    uv run --with-requirements requirements.txt build.py [--quiet]
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
CONTENT = SITE / "content"
TEMPLATES = SITE / "templates"
ASSETS = SITE / "assets"
MANIFEST = SITE / ".build-manifest.json"

SITE_URL = "https://tyscalia.github.io"
AUTHOR = "Tyscalia"
SITE_DESCRIPTION = "Writing by Tyscalia. Reading, and what a text does to the person holding it."
FEED_TITLE = "Tyscalia"

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

md = MarkdownIt("commonmark", {"html": False, "typographer": False})

PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


# --------------------------------------------------------------------------- #
# content


@dataclass
class Doc:
    """One markdown file, flattened into what the templates need."""

    title: str
    body_html: str
    source: Path
    slug: str
    kind: str  # "piece" | "page" | "index"
    date: dt.date | None = None
    summary: str = ""
    hidden: bool = False
    tags: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        """Root-relative URL, with the trailing slash Pages will redirect to."""
        if self.kind == "index":
            return "/"
        prefix = "pieces" if self.kind == "piece" else ""
        return f"/{prefix}/{self.slug}/" if prefix else f"/{self.slug}/"

    @property
    def out_path(self) -> Path:
        if self.kind == "index":
            return ROOT / "index.html"
        if self.kind == "piece":
            return ROOT / "pieces" / self.slug / "index.html"
        return ROOT / self.slug / "index.html"

    @property
    def date_iso(self) -> str:
        return self.date.isoformat() if self.date else ""

    @property
    def date_human(self) -> str:
        if not self.date:
            return ""
        return f"{self.date.day} {MONTHS[self.date.month - 1]} {self.date.year}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"


def parse_front_matter(text: str, source: Path) -> tuple[dict, str]:
    """Split a leading --- yaml --- block from the body."""
    if not text.startswith("---"):
        raise ValueError(f"{source}: missing front matter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{source}: unterminated front matter")
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{source}: front matter is not a mapping")
    return meta, parts[2].lstrip("\n")


def load_docs() -> list[Doc]:
    docs: list[Doc] = []
    for path in sorted(CONTENT.rglob("*.md")):
        rel = path.relative_to(CONTENT)
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)

        if rel.name == "index.md":
            kind = "index"
        elif rel.parts[0] == "pieces":
            kind = "piece"
        elif len(rel.parts) == 1:
            kind = "page"
        else:
            raise ValueError(f"{path}: content must live in pieces/ or at the top level")

        title = meta.get("title") or path.stem
        default_slug = path.stem
        if kind == "piece":
            default_slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)

        date = meta.get("date")
        if isinstance(date, str):
            date = dt.date.fromisoformat(date)
        if kind == "piece" and not date:
            raise ValueError(f"{path}: pieces need a date")

        docs.append(
            Doc(
                title=str(title),
                body_html=md.render(body),
                source=path,
                slug=str(meta["slug"]) if meta.get("slug") else default_slug,
                kind=kind,
                date=date,
                summary=str(meta.get("summary", "")),
                hidden=bool(meta.get("hidden", False)),
                tags=[str(t) for t in meta.get("tags", [])],
            )
        )
    return docs


# --------------------------------------------------------------------------- #
# rendering


def load_template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def render(template: str, **ctx: str) -> str:
    """Substitute {{ key }}. Values are inserted verbatim: escape at the call site."""
    def sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in ctx:
            raise KeyError(f"template placeholder {{{{{key}}}}} has no value")
        return ctx[key]

    return PLACEHOLDER.sub(sub, template)


def page_html(title: str, description: str, content: str) -> str:
    return render(
        load_template("base.html"),
        head_title=html.escape(title),
        description=html.escape(description),
        content=content,
    )


def render_piece(doc: Doc) -> str:
    body = render(
        load_template("piece.html"),
        title=html.escape(doc.title),
        date_iso=doc.date_iso,
        date_human=doc.date_human,
        body=doc.body_html,
    )
    description = doc.summary or SITE_DESCRIPTION
    return page_html(f"{doc.title} | {AUTHOR}", description, body)


def render_page(doc: Doc) -> str:
    body = render(
        load_template("page.html"),
        title=html.escape(doc.title),
        body=doc.body_html,
    )
    return page_html(f"{doc.title} | {AUTHOR}", doc.summary or SITE_DESCRIPTION, body)


def render_index(doc: Doc, pieces: list[Doc]) -> str:
    items = "\n".join(
        render(
            load_template("piece_item.html"),
            url=p.url,
            title=html.escape(p.title),
            date_iso=p.date_iso,
            date_human=p.date_human,
            summary=html.escape(p.summary),
        )
        for p in pieces
    )
    body = render(
        load_template("index.html"),
        title=html.escape(doc.title),
        lede=doc.body_html,
        items=items,
    )
    return page_html(doc.title, SITE_DESCRIPTION, body)


def render_feed(pieces: list[Doc]) -> str:
    entries = "\n".join(
        render(
            load_template("feed_entry.xml"),
            url=SITE_URL + p.url,
            title=html.escape(p.title),
            updated=f"{p.date_iso}T00:00:00Z",
            summary=html.escape(p.summary),
            content=html.escape(p.body_html),
        )
        for p in pieces
    )
    return render(
        load_template("feed.xml"),
        site_url=SITE_URL,
        feed_title=FEED_TITLE,
        author=AUTHOR,
        updated=f"{pieces[0].date_iso}T00:00:00Z" if pieces else "1970-01-01T00:00:00Z",
        entries=entries,
    )


def render_sitemap(pages: list[Doc]) -> str:
    urls = "\n".join(
        render(
            load_template("sitemap_url.xml"),
            loc=SITE_URL + d.url,
            lastmod=d.date_iso,
        )
        for d in pages
    )
    return render(load_template("sitemap.xml"), urls=urls)


# --------------------------------------------------------------------------- #
# build


def owned_paths() -> list[Path]:
    """Paths we generated last time, so this build can clear exactly those."""
    if not MANIFEST.exists():
        return []
    return [ROOT / p for p in json.loads(MANIFEST.read_text(encoding="utf-8"))]


def clean_previous() -> None:
    for path in owned_paths():
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def write(path: Path, text: str, written: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    written.append(str(path.relative_to(ROOT)))


def build(quiet: bool = False) -> list[str]:
    docs = load_docs()
    index = [d for d in docs if d.kind == "index"]
    pieces = sorted(
        [d for d in docs if d.kind == "piece" and not d.hidden],
        key=lambda d: (d.date, d.slug),
        reverse=True,
    )
    pages = [d for d in docs if d.kind == "page" and not d.hidden]

    if len(index) != 1:
        raise ValueError(f"expected exactly one site/content/index.md, found {len(index)}")

    written: list[str] = []

    write(index[0].out_path, render_index(index[0], pieces), written)
    for doc in pages:
        write(doc.out_path, render_page(doc), written)
    for doc in pieces:
        write(doc.out_path, render_piece(doc), written)

    write(ROOT / "feed.xml", render_feed(pieces), written)
    write(ROOT / "sitemap.xml", render_sitemap([index[0], *pages, *pieces]), written)

    for asset in sorted(ASSETS.rglob("*")):
        if asset.is_dir():
            continue
        target = ROOT / asset.relative_to(ASSETS)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, target)
        written.append(str(target.relative_to(ROOT)))

    MANIFEST.write_text(json.dumps(written, indent=1) + "\n", encoding="utf-8")

    if not quiet:
        for name in written:
            print(f"  {name}")
        print(f"built {len(written)} files: {len(pieces)} piece(s), {len(pages)} page(s)")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build tyscalia.github.io.")
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument(
        "--keep", action="store_true", help="do not clear the previous build first"
    )
    args = parser.parse_args(argv)

    if not args.keep:
        clean_previous()
    build(quiet=args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
