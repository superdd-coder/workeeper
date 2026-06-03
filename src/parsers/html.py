from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from src.parsers.base import DocumentParser, ParsedDocument

# Tags to strip entirely (content removed)
STRIP_TAGS = ["script", "style", "nav", "footer", "header", "noscript"]

# Heading tags mapped to Markdown prefixes
HEADINGS = {f"h{i}": f"{'#' * i} " for i in range(1, 7)}


class HTMLParser(DocumentParser):
    def parse(self, path: Path) -> ParsedDocument:
        raw = path.read_bytes()
        soup = BeautifulSoup(raw, "html.parser")

        # Extract title before stripping
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None

        # Remove unwanted tags
        for tag_name in STRIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Convert headings to Markdown-style
        for tag_name, prefix in HEADINGS.items():
            for tag in soup.find_all(tag_name):
                tag.replace_with(f"\n{prefix}{tag.get_text(strip=True)}\n")

        # Extract text from <body>, falling back to full document
        body = soup.find("body")
        source = body if body else soup
        text = source.get_text(separator="\n")

        # Collapse excessive blank lines
        lines = [line.strip() for line in text.splitlines()]
        content = "\n".join(line for line in lines if line)

        metadata: dict = {"format": "html"}
        if title:
            metadata["title"] = title

        return ParsedDocument(
            content=content,
            metadata=metadata,
            source_path=str(path),
            file_type="html",
        )
