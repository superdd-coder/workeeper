from pathlib import Path

import yaml

from src.parsers.base import DocumentParser, ParsedDocument

_FRONTMATTER_DELIMITER = "---"


def _extract_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML front-matter between '---' delimiters.

    Returns (frontmatter_dict, body_text). If no front-matter is found,
    returns ({}, original_text).
    """
    if not text.startswith(_FRONTMATTER_DELIMITER + "\n"):
        return {}, text

    # Find the closing delimiter
    end_idx = text.find("\n" + _FRONTMATTER_DELIMITER, len(_FRONTMATTER_DELIMITER) + 1)
    if end_idx == -1:
        return {}, text

    yaml_block = text[len(_FRONTMATTER_DELIMITER) + 1 : end_idx]
    body = text[end_idx + len("\n" + _FRONTMATTER_DELIMITER) :].lstrip("\n")

    try:
        metadata = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError:
        metadata = {}

    return metadata, body


class MarkdownParser(DocumentParser):
    def parse(self, path: Path) -> ParsedDocument:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = _extract_frontmatter(text)

        meta: dict = {"format": "markdown"}
        if frontmatter:
            meta["frontmatter"] = frontmatter

        return ParsedDocument(
            content=body,
            metadata=meta,
            source_path=str(path),
            file_type="markdown",
        )
