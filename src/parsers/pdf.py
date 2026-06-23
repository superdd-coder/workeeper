from __future__ import annotations

import re
from pathlib import Path

from src.parsers.base import DocumentParser, ParsedDocument


def _bbox_in_table(bbox: tuple, table_bboxes: list[tuple]) -> bool:
    """Check if a y-position falls inside any table region."""
    y = bbox[1] if isinstance(bbox, tuple) else bbox
    for ty0, _, ty1, _ in table_bboxes:
        if ty0 - 5 <= y <= ty1 + 5:
            return True
    return False


def _table_data_to_markdown(data: list[list[str | None]]) -> str:
    """Convert pdfplumber table data (list of lists) to markdown.

    Strips entirely empty rows and columns before rendering.
    """
    if not data or not data[0]:
        return ""

    cleaned: list[list[str]] = []
    for row in data:
        cells = [str(c).replace("\n", " ").strip() if c else "" for c in row]
        # Skip entirely empty rows
        if any(c for c in cells):
            cleaned.append(cells)

    if not cleaned:
        return ""

    # Pad to uniform column count
    num_cols = max(len(row) for row in cleaned)
    for row in cleaned:
        while len(row) < num_cols:
            row.append("")

    # Remove entirely empty columns
    keep_cols: list[int] = []
    for ci in range(num_cols):
        if any(row[ci] for row in cleaned):
            keep_cols.append(ci)

    if not keep_cols:
        return ""

    pruned = [[row[ci] for ci in keep_cols] for row in cleaned]

    header = pruned[0]
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in pruned[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _ocr_page(page_image, lang: str = "chi_sim+eng") -> str:
    """Extract text from a page image using Tesseract OCR."""
    try:
        import pytesseract
        text = pytesseract.image_to_string(page_image, lang=lang)
        return text.strip()
    except Exception:
        return ""


def _parse_with_pdfplumber(path: Path) -> tuple[list[str], bool]:
    """Parse PDF using pdfplumber: text extraction + table detection.

    Maintains document layout order by sorting text blocks and tables
    by their vertical position on the page.
    Falls back to OCR for image-based (scanned) pages via pypdfium2.
    """
    import pdfplumber

    pdf = pdfplumber.open(str(path))
    pages: list[str] = []
    has_any_table = False

    for page in pdf.pages:
        tables = page.find_tables()

        if tables:
            has_any_table = True
            table_bboxes = [t.bbox for t in tables]
            elements: list[tuple[float, str, str]] = []

            # Convert each table to markdown.
            # Skip single-column "tables" — they are usually just text wrappers.
            for table in tables:
                try:
                    data = table.extract()
                    if data and data[0]:
                        col_count = len(data[0])
                        if col_count < 2:
                            continue  # skip single-column wrappers
                        md = _table_data_to_markdown(data)
                        if md:
                            elements.append((table.bbox[1], "table", md))
                except Exception:
                    pass

            # Get text outside table regions.
            # pdfplumber extracts text from the full page; we interpolate
            # the tables by their y-position and keep surrounding text.
            full_text = page.extract_text() or ""
            if full_text.strip():
                elements.append((0, "text", full_text))

            elements.sort(key=lambda e: e[0])
            text = "\n\n".join(e[2] for e in elements)
        else:
            text = page.extract_text() or ""

        # Fallback to OCR if no text extracted (scanned/image-based page)
        if not text.strip():
            text = _ocr_page(page.to_image(resolution=300).original)

        pages.append(text)

    pdf.close()
    return pages, has_any_table


class PDFParser(DocumentParser):
    def parse(self, path: Path) -> ParsedDocument:
        text_pages, tables_found = _parse_with_pdfplumber(path)

        cleaned = []
        for page_text in text_pages:
            page_text = page_text.strip()
            # Remove standalone page numbers at start of page
            page_text = re.sub(
                r'^\d{1,3}\s*$', '', page_text, count=1, flags=re.MULTILINE
            )
            cleaned.append(page_text)

        # Build content with position_map tracking page boundaries
        position_map: list[dict] = []
        parts: list[str] = []
        offset = 0
        for i, page_text in enumerate(cleaned):
            position_map.append({
                "char_offset": offset,
                "label": f"Page {i + 1}",
                "type": "page",
                "page_number": i + 1,
            })
            parts.append(page_text)
            offset += len(page_text) + 2  # +2 for "\n\n" separator

        return ParsedDocument(
            content="\n\n".join(parts),
            metadata={"pages": len(cleaned), "tables_found": tables_found},
            source_path=str(path),
            file_type="pdf",
            position_map=position_map,
        )
