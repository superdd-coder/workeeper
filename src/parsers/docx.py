"""DOCX parser using mammoth for Markdown output.

Converts .docx files to Markdown via mammoth, preserving formatting
(bold, italic, lists, headings, tables) that python-docx's para.text drops.
Output uses file_type="markdown" so it routes to MarkdownChunker.
"""

from __future__ import annotations

import re
from pathlib import Path

import mammoth

from src.parsers.base import DocumentParser, ParsedDocument


def clean_mammoth_markdown(text: str) -> str:
    """Clean mammoth's Markdown output.

    mammoth produces valid but noisy Markdown: unnecessary backslash escaping,
    __ for bold instead of **, and Word hidden bookmark anchors.
    """
    # 1. Remove Word hidden bookmark anchors (e.g. <a id="_Hlk12345"></a>)
    text = re.sub(r'<a id="[^"]*"></a>', "", text)

    # 2. Remove unnecessary backslash escaping mammoth adds for punctuation/brackets.
    #    Do NOT remove \_ (valid Markdown for literal underscore) or \* (literal asterisk).
    text = re.sub(r"\\([()[\].,:;!\"#&=<>|~`{}\-+])", r"\1", text)

    # 3. Convert mammoth's __bold__ to **bold** (only real paired markers, not __ in \_)
    text = re.sub(r"__(.+?)__", r"**\1**", text)

    # 4. Clean up empty/trailing-whitespace bold markers (e.g. "** " or "** **")
    text = re.sub(r"\*\*\s+\*\*", "", text)

    return text


class DocxParser(DocumentParser):
    def parse(self, path: Path) -> ParsedDocument:
        with open(str(path), "rb") as f:
            result = mammoth.convert_to_markdown(f)

        text = clean_mammoth_markdown(result.value)

        # Build position_map from heading positions
        position_map: list[dict] = []
        for m in re.finditer(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE):
            position_map.append({
                "char_offset": m.start(),
                "label": m.group(0).strip(),
                "type": "section",
            })

        messages = [str(m) for m in result.messages] if result.messages else []

        return ParsedDocument(
            content=text,
            metadata={"format": "markdown", "messages": messages},
            source_path=str(path),
            file_type="markdown",
            position_map=position_map,
        )
