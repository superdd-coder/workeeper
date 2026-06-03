from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedDocument:
    content: str
    metadata: dict = field(default_factory=dict)
    source_path: str = ""
    file_type: str = ""


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, path: Path) -> ParsedDocument: ...
