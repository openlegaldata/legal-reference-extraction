from __future__ import annotations

import logging
import uuid
from enum import Enum

logger = logging.getLogger(__name__)


class RefType(Enum):
    """Type of referenced document"""

    CASE = "case"
    LAW = "law"


class BaseRef:
    ref_type: RefType | None = None

    def __init__(
        self,
        ref_type: RefType | None = None,
        book: str = "",
        section: str = "",
        file_number: str = "",
        ecli: str = "",
        court: str = "",
        date: str = "",
    ):
        # B2: explicit fields instead of **kwargs
        self.ref_type = ref_type
        self.book = book
        self.section = section
        self.file_number = file_number
        self.ecli = ecli
        self.court = court
        self.date = date

    def __hash__(self):
        # B4: hash the full field tuple, not __repr__
        return hash(
            (
                self.ref_type,
                self.book,
                self.section,
                self.file_number,
                self.ecli,
                self.court,
                self.date,
            )
        )


class CaseRefMixin(BaseRef):
    file_number: str = ""
    ecli: str = ""
    court: str = ""
    date: str = ""


class LawRefMixin(BaseRef):
    book: str = ""
    section: str = ""

    @staticmethod
    def init_law(book, section):
        return Ref(
            ref_type=RefType.LAW,
            book=LawRefMixin.clean_book(book),
            section=LawRefMixin.clean_section(section),
        )

    @staticmethod
    def clean_book(book: str | None) -> str | None:
        if book is None:
            return None
        return book.strip().lower()

    @staticmethod
    def clean_section(sect: str) -> str:
        return sect.replace(" ", "").lower()


class Ref(LawRefMixin, CaseRefMixin, BaseRef):
    """
    A reference can point to all available types (RefType). Currently either law or case supported.

    """

    def __lt__(self, other):
        # Used by tests/conftest.py::assert_refs to sort ref lists before
        # comparison.  Only ``<`` is actually exercised.
        if not isinstance(other, Ref):
            return NotImplemented
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
        # B3: return NotImplemented for foreign types instead of assert
        if not isinstance(other, Ref):
            return NotImplemented
        return (
            self.ref_type == other.ref_type
            and self.book == other.book
            and self.section == other.section
            and self.file_number == other.file_number
            and self.ecli == other.ecli
            and self.court == other.court
            and self.date == other.date
        )

    def __repr__(self):
        if self.ref_type == RefType.LAW:
            data = f"{self.book}/{self.section}"
        elif self.ref_type == RefType.CASE:
            data = f"{self.court}/{self.file_number}/{self.date}"
        else:
            raise ValueError(f"Unsupported ref type: {self.ref_type}")

        return f"<Ref({self.ref_type.value}: {data})>"


class RefMarker:
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

    # Set by django
    referenced_by = None
    referenced_by_type = None

    def __init__(self, text: str, start: int, end: int, line=""):
        self.text = text
        self.start = start
        self.end = end
        self.line = line
        # B1: instance-level list instead of mutable class default
        self.references: list[Ref] = []

    def replace_content_with_mask(self, content):
        mask = "_" * (self.end - self.start)
        return content[: self.start] + mask + content[self.end :]

    def set_uuid(self):
        self.uuid = uuid.uuid4()

    def set_references(self, refs: list[Ref]):
        self.references = refs

    def get_references(self) -> list[Ref]:
        return self.references

    def __repr__(self):
        return f"<RefMarker({self.__dict__})>"
