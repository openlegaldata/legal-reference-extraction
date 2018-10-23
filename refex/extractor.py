import logging
import re

from refex.extractors.case import CaseRefExtractorMixin
from refex.extractors.law import LawRefExtractorMixin

logger = logging.getLogger(__name__)


class RefExtractor(LawRefExtractorMixin, CaseRefExtractorMixin):

    do_law_refs = True
    do_case_refs = True

    def extract(self, content_html: str):
        reference_markers = []

        # Remove all reference markers (HTML or MarkDown)
        content = self.remove_markers(content_html)

        if self.do_law_refs:
            content, refs = self.extract_law_ref_markers(content)
            reference_markers.extend(refs)

            logger.debug('Extracted law refs: %i' % len(refs))

        if self.do_case_refs:
            content, refs = self.extract_case_ref_markers(content)
            reference_markers.extend(refs)

            logger.debug('Extracted case refs: %i' % len(refs))

        content_with_markers = content

        return content_with_markers, reference_markers

    @staticmethod
    def remove_markers(value):
        return re.sub(r'\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]', r'\2', value)

    @staticmethod
    def make_markers_clickable(value):
        """
        TODO Replace ref marker number with db id
        """
        return re.sub(r'\[ref=([-a-z0-9]+)\](.*?)\[\/ref\]', r'<a href="#refs" onclick="clickRefMarker(this);" data-ref-uuid="\1" class="ref">\2</a>', value)

