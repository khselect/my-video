#!/usr/bin/env python3
"""Extract a lecture source (PDF / HTML / Markdown / text) into <project>/source/.

usage: extract_source.py <document> <project-dir> [--no-pages]

Writes source/source.md (PDF pages separated by '## [p.N]') and, for PDFs,
source/pages/page-N.png at 150 dpi so real figures can be shown on screen.
Needs poppler-utils (pdftotext, pdftoppm) for PDFs; bs4 optional for HTML.
"""
import argparse
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path


def pdf_to_md(pdf: Path) -> str:
    if not shutil.which("pdftotext"):
        sys.exit("pdftotext not found: install poppler-utils (brew install poppler / apt install poppler-utils)")
    raw = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    pages = raw.split("\f")
    out = []
    for i, page in enumerate(pages, 1):
        text = page.strip()
        if text:
            out.append(f"## [p.{i}]\n\n{text}\n")
    return "\n".join(out)


def html_to_md(path: Path) -> str:
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", src, flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>|</p>|</h\d>|</li>", "\n", text, flags=re.I)
        return html.unescape(re.sub(r"<[^>]+>", "", text))
    soup = BeautifulSoup(src, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    lines = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "blockquote", "td"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            lines.append("\n" + "#" * int(el.name[1]) + " " + text)
        elif el.name == "li":
            lines.append("- " + text)
        elif el.name == "pre":
            lines.append("```\n" + el.get_text() + "\n```")
        else:
            lines.append(text)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("document", type=Path)
    ap.add_argument("project", type=Path)
    ap.add_argument("--no-pages", action="store_true", help="skip PDF page images")
    a = ap.parse_args()

    out_dir = a.project / "source"
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = a.document.suffix.lower()
    if ext == ".pdf":
        md = pdf_to_md(a.document)
        if not a.no_pages and shutil.which("pdftoppm"):
            (out_dir / "pages").mkdir(exist_ok=True)
            subprocess.run(["pdftoppm", "-png", "-r", "150", str(a.document), str(out_dir / "pages" / "page")], check=True)
    elif ext in (".html", ".htm"):
        md = html_to_md(a.document)
    else:
        md = a.document.read_text(encoding="utf-8", errors="replace")

    md = re.sub(r"\n{3,}", "\n\n", md)
    (out_dir / "source.md").write_text(md, encoding="utf-8")
    shutil.copy(a.document, out_dir / ("original" + ext))
    print(f"source.md: {len(md):,} chars -> {out_dir / 'source.md'}")
    pages = sorted((out_dir / "pages").glob("*.png")) if (out_dir / "pages").exists() else []
    if pages:
        print(f"page images: {len(pages)} -> {out_dir / 'pages'}")


if __name__ == "__main__":
    main()
