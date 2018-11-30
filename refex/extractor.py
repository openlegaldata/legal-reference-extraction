import logging
import re
from typing import List

from refex.extractors.case import CaseRefExtractorMixin
from refex.extractors.law import LawRefExtractorMixin
from refex.models import RefMarker

logger = logging.getLogger(__name__)


class RefExtractor(LawRefExtractorMixin, CaseRefExtractorMixin):
    """

    Reference marker format: [ref=UUID]...[/ref]

    """

    do_law_refs = True
    do_case_refs = True

    def extract(self, content_html: str):
        reference_markers = []  # type: List[RefMarker]

        # Remove all reference markers (HTML or MarkDown)
        content = self.remove_markers(content_html)

        if self.do_law_refs:
            refs = self.extract_law_ref_markers(content)
            reference_markers.extend(refs)

            logger.debug('Extracted law refs: %i' % len(refs))

        if self.do_case_refs:
            refs = self.extract_case_ref_markers(content)
            reference_markers.extend(refs)

            logger.debug('Extracted case refs: %i' % len(refs))

        # Add markers to content
        marker_offset = 0
        content_with_markers = content
        sorted_markers = sorted(reference_markers, key=lambda k: k.get_start_position())  # order by occurrence in text

        for i, marker in enumerate(sorted_markers):
            # Check on overlaps
            if i > 0 and sorted_markers[i - 1].get_end_positon() >= marker.get_start_position():
                raise ValueError('Marker overlaps with previous marker: %s' % marker)
            elif i + 1 < len(sorted_markers) and sorted_markers[i + 1].get_start_position() <= marker.get_end_positon():
                raise ValueError('Marker overlaps with next marker: %s' % marker)
            else:
                # Everything fine, replace content
                content_with_markers, marker_offset = marker.replace_content(content_with_markers, marker_offset)

        return content_with_markers, reference_markers

    @staticmethod
    def remove_markers(value):
        return re.sub(r'\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]', r'\2', value)
