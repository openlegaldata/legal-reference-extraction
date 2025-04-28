import logging
import uuid
from enum import Enum
from functools import total_ordering
from typing import List, Tuple, Optional

from refex import MARKER_OPEN_FORMAT, MARKER_CLOSE_FORMAT

logger = logging.getLogger(__name__)


class RefType(Enum):
    """Type of referenced document"""

    CASE = "case"
    LAW = "law"


class BaseRef(object):
    ref_type: Optional[RefType] = None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __hash__(self):
        return hash(self.__repr__())


class CaseRefMixin(BaseRef):
    file_number: str = ""
    ecli: str = ""
    court: str = ""
    date: str = ""

    def get_case_repr(self) -> str:
        return "%s/%s/%s" % (self.court, self.file_number, self.date)


class LawRefMixin(BaseRef):
    book: str = ""
    section: str = ""
    sentence: str = ""

    @staticmethod
    def init_law(book, section):
        return Ref(
            ref_type=RefType.LAW,
            book=LawRefMixin.clean_book(book),
            section=LawRefMixin.clean_section(section),
        )

    @staticmethod
    def clean_book(book: Optional[str]) -> Optional[str]:
        if book is None:
            return None
        return book.strip().lower()

    @staticmethod
    def clean_section(sect: str) -> str:
        return sect.replace(" ", "").lower()

    def get_law_repr(self):
        return "%s/%s" % (self.book, self.section)


@total_ordering
class Ref(LawRefMixin, CaseRefMixin, BaseRef):
    """
    A reference can point to all available types (RefType). Currently either law or case supported.

    """

    def __lt__(self, other):
        assert isinstance(other, Ref)
        # return self.__repr__() < other.__repr__()
        return (
            self.ref_type.value,
            self.book,
            self.section,
            self.court,
            self.file_number,
        ) < (
            other.ref_type.value,
            other.book,
            other.section,
            other.court,
            other.file_number,
        )

    def __eq__(self, other):
        assert isinstance(other, Ref)  # assumption for this example
        return self.__dict__ == other.__dict__

    def __repr__(self):
        if self.ref_type == RefType.LAW:
            data = self.get_law_repr()
        elif self.ref_type == RefType.CASE:
            data = self.get_case_repr()
        else:
            raise ValueError("Unsupported ref type: %s" % self.ref_type)

        return "<Ref(%s: %s)>" % (self.ref_type.value, data)
        # return 'Ref<%s>' % self.__dict__
        # return 'Ref<%s>' % sorted(self.__dict__.items(), key=lambda x: x[0])


class RefMarker(object):
    """
    Abstract class for reference markers, i.e. the actual reference within a text "§§ 12-14 BGB".

    Marker has a position (start, end, line), unique identifier (uuid, randomly generated), text of the marker as in
    the text, list of references (can be law, case, ...). Implementations of abstract class (LawReferenceMarker, ...)
    have the corresponding source object (LawReferenceMarker: referenced_by = a law object).

    """

    text: str = ""  # Text of marker
    uuid: str = ""
    start: int = 0
    end: int = 0
    line: str = ""  # Line cannot be used with HTML content
    references: List[Ref] = []

    # Set by django
    referenced_by = None
    referenced_by_type = None

    def __init__(self, text: str, start: int, end: int, line=""):
        self.text = text
        self.start = start
        self.end = end
        self.line = line

    def replace_content(self, content, marker_offset) -> Tuple[str, int]:

        start = self.start + marker_offset
        end = self.end + marker_offset

        # marker_open = '[ref=%i]' % key
        # Instead of key use uuid
        marker_open = MARKER_OPEN_FORMAT % self.__dict__
        marker_close = MARKER_CLOSE_FORMAT % self.__dict__

        marker_offset += len(marker_open) + len(marker_close)

        # double replacements
        # alternative: content[start:end]
        content = (
            content[:start] + marker_open + self.text + marker_close + content[end:]
        )

        return content, marker_offset

    def replace_content_with_mask(self, content):
        mask = "_" * self.get_length()  # length of marker

        return content[: self.start] + mask + content[self.end :]

    def set_uuid(self):
        self.uuid = uuid.uuid4()

    def set_references(self, refs: List[Ref]):
        self.references = refs

    def get_references(self) -> List[Ref]:
        return self.references

    def get_start_position(self):
        return self.start

    def get_end_position(self):
        return self.end

    def get_length(self):
        return self.end - self.start

    def __repr__(self):
        return "<RefMarker(%s)>" % self.__dict__
