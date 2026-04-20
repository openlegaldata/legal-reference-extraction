import logging
import re
import warnings

from refex.extractors.case import CaseRefExtractorMixin
from refex.extractors.law_dnc import DivideAndConquerLawRefExtractorMixin
from refex.models import RefMarker
from refex.orchestrator import CitationExtractor

logger = logging.getLogger(__name__)


class RefExtractor(DivideAndConquerLawRefExtractorMixin, CaseRefExtractorMixin):
    """Legacy extractor API — use ``CitationExtractor`` for new code.

    .. deprecated:: 0.7.0
       Use :class:`refex.orchestrator.CitationExtractor` instead.

    New consumers should use::

        from refex.orchestrator import CitationExtractor
        extractor = CitationExtractor()
        result = extractor.extract(text)
    """

    do_law_refs = True
    do_case_refs = True

    def extract(self, content_html: str, is_html: bool = False) -> tuple[str, list[RefMarker]]:
        """Extract references and return ``(content, markers)``.

        .. deprecated:: 0.7.0
           The first element of the tuple (content with ``[ref=...]``
           markers) is now always the plain input text.  Use
           ``CitationExtractor`` for new code.
        """
        if is_html:
            warnings.warn(
                "is_html is deprecated. Use CitationExtractor with format='html' instead: "
                "CitationExtractor().extract(text, fmt='html')",
                DeprecationWarning,
                stacklevel=2,
            )

        reference_markers: list[RefMarker] = []

        content = self.remove_markers(content_html)

        if self.do_law_refs:
            markers = self.extract_law_ref_markers(content, is_html)
            reference_markers.extend(markers)

            logger.debug("Extracted law ref markers: %i", len(markers))

        if self.do_case_refs:
            markers = self.extract_case_ref_markers(content)
            reference_markers.extend(markers)

            logger.debug("Extracted case ref markers: %i", len(markers))

        # H2: No longer inserts [ref=UUID]...[/ref] markers into content.
        # The first tuple element is now the plain text for backward compat.
        return content, reference_markers

    def extract_citations(self, text: str, **kwargs):
        """Extract citations using the new typed API.

        This is the recommended method for new code.  Returns an
        ``ExtractionResult`` with typed ``Citation`` objects.

        Args:
            text: Plain text or HTML content.
            **kwargs: Passed to ``CitationExtractor.extract()``
                      (e.g. ``fmt="html"``).
        """
        extractor = CitationExtractor()
        return extractor.extract(text, **kwargs)

    @staticmethod
    def remove_markers(value: str) -> str:
        return re.sub(r"\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]", r"\2", value)
