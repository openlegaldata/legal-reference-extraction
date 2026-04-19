"""Extractor protocol (C2) — the strategy interface.

Any extraction engine (regex, CRF, transformer) implements this protocol.
The ``RefExtractor`` orchestrator accepts a list of ``Extractor`` instances
and merges their results.
"""

from __future__ import annotations

from typing import Protocol

from refex.citations import Citation, CitationRelation


class Extractor(Protocol):
    """Protocol for citation extraction engines."""

    def extract(self, text: str) -> tuple[list[Citation], list[CitationRelation]]:
        """Extract citations and relations from plain text.

        Args:
            text: The plain-text document content.

        Returns:
            A tuple of (citations, relations).
        """
        ...
