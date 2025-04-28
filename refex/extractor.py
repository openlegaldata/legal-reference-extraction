import logging
import re
from typing import List, Tuple

from refex.errors import RefExError
from refex.extractors.case import CaseRefExtractorMixin
from refex.extractors.law_dnc import DivideAndConquerLawRefExtractorMixin
from refex.models import RefMarker

logger = logging.getLogger(__name__)


class RefExtractor(
    DivideAndConquerLawRefExtractorMixin, CaseRefExtractorMixin
):  # LawRefExtractorMixin
    """

    Reference marker format: [ref=UUID]...[/ref]

    """

    do_law_refs = True
    do_case_refs = True

    def replace_content(self, content, reference_markers):
        """
        Replace content with markers

        :param content: Without markers
        :param reference_markers:
        :return:
        """
        marker_offset = 0
        content_with_markers = content
        sorted_markers = sorted(
            reference_markers, key=lambda k: k.get_start_position()
        )  # order by occurrence in text

        for i, marker in enumerate(sorted_markers):
            # Check on overlaps
            if (
                i > 0
                and sorted_markers[i - 1].get_end_position()
                >= marker.get_start_position()
            ):
                raise RefExError("Marker overlaps with previous marker: %s" % marker)
            elif (
                i + 1 < len(sorted_markers)
                and sorted_markers[i + 1].get_start_position()
                <= marker.get_end_position()
            ):
                raise RefExError("Marker overlaps with next marker: %s" % marker)
            else:
                # Everything fine, replace content
                content_with_markers, marker_offset = marker.replace_content(
                    content_with_markers, marker_offset
                )

        return content_with_markers

    def extract(
        self, content_html: str, is_html: bool = False
    ) -> Tuple[str, List[RefMarker]]:

        reference_markers: List[RefMarker] = []

        # Remove all reference markers (HTML or MarkDown)
        content = self.remove_markers(content_html)

        if self.do_law_refs:
            markers = self.extract_law_ref_markers(content, is_html)
            reference_markers.extend(markers)

            logger.debug("Extracted law ref markers: %i" % len(markers))

        if self.do_case_refs:
            markers = self.extract_case_ref_markers(content)
            reference_markers.extend(markers)

            logger.debug("Extracted case ref markers: %i" % len(markers))

        # Add markers to content
        content_with_markers = self.replace_content(content, reference_markers)

        return content_with_markers, reference_markers

    @staticmethod
    def remove_markers(value: str) -> str:
        return re.sub(r"\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]", r"\2", value)
