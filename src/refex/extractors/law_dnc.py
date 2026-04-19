import logging
import re

from refex.errors import RefExError
from refex.models import Ref, RefMarker, RefType

logger = logging.getLogger(__name__)


class DivideAndConquerLawRefExtractorMixin:
    """
    Extractor for law references (citations of legislation). Each law is identified by a section (§, consisting of
    numbers and letters) and the corresponding code as abbreviation or full name (BGB, Bürgerliches Gesetzbuch).

    We distinguish between single references (one marker => one law, e.g. § 1 ABC) and multi references (one marker =>
    multiple laws, e.g. §§ 1,2-5 ABC).

    Example citations:

    § 7 Abs. 1 S. 2 MilchSoPrG
    § 25 SGB VIII
    § 40 des Verwaltungsverfahrensgesetzes
    § 433 Abs. 1 S. 1 BGB

    """

    # Used when reference has only section but no book
    # (citations within a law book to other sections, § 1 AB -> § 2 AB)
    law_book_context = None

    # B6: default_law_book_codes as class constant (immutable reference list)
    default_law_book_codes = [
        "AsylG",
        "BGB",
        "GG",
        "VwGO",
        "GkG",
        "stbstg",
        "lbo",
        "ZPO",
        "LVwG",
        "AGVwGO SH",
        "BauGB",
        "BauNVO",
        "ZWStS",
        "SbStG",
        "StPO",
        "TKG",
        "SG",
        "SGG",
        "SGB X",
    ]

    # B5: pre-compiled book regex pattern (built once per init)
    _book_ref_regex: str | None = None

    # All text non-word symbols
    _default_word_delimiter = r"\s|\.|,|;|:|!|\?|\(|\)|\[|\]|\"|'|<|>|&"

    def __init__(self):
        # B6: instance-level copy, not shared class state
        self._law_book_codes: list[str] = list(self.default_law_book_codes)
        # B5: pre-compile the book regex once
        self._book_ref_regex = self._build_law_book_ref_regex(self._law_book_codes)

    @property
    def law_book_codes(self) -> list[str]:
        return self._law_book_codes

    @law_book_codes.setter
    def law_book_codes(self, codes: list[str] | None):
        self._law_book_codes = list(codes) if codes else list(self.default_law_book_codes)
        self._book_ref_regex = self._build_law_book_ref_regex(self._law_book_codes)

    def extract_law_ref_markers(self, content: str, is_html: bool = False) -> list[RefMarker]:
        """
        The main extraction method. Takes input content and returns list of extracted reference markers.

        Divide and Conquer:
        - only simple regex
        - replace matches with mask to avoid multiple matches

        :param content: Plain-text or even HTML
        :return: List of reference markers
        """

        if self.law_book_context is not None:
            return self.extract_law_ref_markers_with_context(content)

        markers = []

        if is_html:
            section_sign = "&#167;"
            word_delimiter = (
                r"\s|\.|,|;|:|!|\?|\(|\)|\[|\]"
                r"|&#8221;|\&#8216;|\&#8217;|&#60;|&#62;|&#38;"
                r"|&rdquo;|\&lsquo;|\&rsquo;|&lt;|&gt;|&amp;"
                r"|\"|'|<|>|&"
            )
        else:
            section_sign = "§"
            word_delimiter = self._default_word_delimiter

        # Use \s for the space after § to handle both regular and non-breaking spaces
        sect_space = r"\s"

        book_look_ahead = "(?=" + word_delimiter + ")"
        book_pattern = self._book_ref_regex

        any_content = r"([0-9]{1,5}|\.|[a-z]|[IXV]{1,3}|Abs\.|Abs|Satz|Halbsatz|S\.|Nr|Nr\.|Alt|Alt\.|und|bis|,|;|\s)*"  # noqa: E501

        # B5: pre-compile patterns
        multi_pattern = re.compile(
            section_sign
            + section_sign
            + sect_space
            + r"(\s|[0-9]+(\.{,1})|[a-z]|Abs\.|Abs|Satz|Halbsatz|S\.|Nr|Nr\.|Alt|Alt\.|f\.|ff\.|und|bis|\,|;|\s"
            + book_pattern
            + r")+\s("
            + book_pattern
            + ")"
            + book_look_ahead
        )

        for marker_match in multi_pattern.finditer(content):
            marker_text = marker_match.group(0)
            refs: list[Ref] = []

            logger.debug("Multi Match with: %s", marker_text)

            book_positions = {}
            for book_match in re.finditer(book_pattern, marker_text):
                book_positions[book_match.start()] = book_match.group(0)

            if len(book_positions) < 0:
                logger.error("No book found in marker text: %s", marker_text)
                continue

            a = r"([0-9]+)\s(?=bis|und)"
            b = r"([0-9]+)\s?[a-z]"
            c = "([0-9]+)"
            ref_pattern = re.compile(
                "(?P<sep>" + section_sign + section_sign + r"|,|;|und|bis)\s?(?P<sect>(" + a + "|" + b + "|" + c + "))"
            )

            for ref_match in ref_pattern.finditer(marker_text):
                sect = ref_match.group("sect")

                logger.debug("Found ref: %s", ref_match.group())

                if len(book_positions) == 1:
                    book = next(iter(book_positions.values()))
                else:
                    book = None
                    pos = ref_match.start()

                    for bp in book_positions:
                        if bp > pos:
                            book = book_positions[bp]
                            break

                if book is None:
                    logger.error("No book after reference found: %s - %s", ref_match.group(0), marker_text)
                    continue

                if ref_match.group("sep") == "bis" and len(refs) > 0:
                    from_sect = refs[-1].section

                    if sect.isdigit() and from_sect.isdigit():
                        for between_sect in range(int(from_sect) + 1, int(sect)):
                            refs.append(Ref.init_law(book=book, section=str(between_sect)))

                refs.append(Ref.init_law(book=book, section=sect))

            marker = RefMarker(text=marker_text, start=marker_match.start(), end=marker_match.end())
            marker.set_uuid()
            marker.set_references(refs)

            if len(refs) > 0:
                markers.append(marker)
                content = marker.replace_content_with_mask(content)
            else:
                logger.warning("No references found in marker: %s ", marker_text)

        # Single refs — use sect_space instead of literal " " after §
        sect_pattern = r"(?P<sect>([0-9]+)(\s?[a-z]?))"
        single_patterns = [
            re.compile(section_sign + sect_space + sect_pattern + " (?P<book>" + book_pattern + ")" + book_look_ahead),
            re.compile(
                section_sign
                + sect_space
                + sect_pattern
                + " Abs. ([0-9]+) Alt. ([0-9]+) (?P<book>"
                + book_pattern
                + ")"
                + book_look_ahead
            ),
            re.compile(
                section_sign
                + sect_space
                + r"(?P<sect>([0-9]+)(\s?[a-z]?)) "
                + any_content
                + " (?P<book>("
                + book_pattern
                + "))"
                + book_look_ahead
            ),
            re.compile(
                section_sign
                + sect_space
                + r"(?P<sect>([0-9]+)(\s?[a-z]?)) "
                + any_content
                + r" (?P<next_book>(i\.V\.m\.|iVm))"
                + book_look_ahead
            ),
        ]

        markers_waiting_for_book: list[RefMarker] = []

        for pattern in single_patterns:
            for marker_match in pattern.finditer(content):
                marker_text = marker_match.group(0)
                if "book" in marker_match.groupdict():
                    book = Ref.clean_book(marker_match.group("book"))
                else:
                    book = None

                ref = Ref.init_law(section=marker_match.group("sect"), book=None)

                marker = RefMarker(text=marker_text, start=marker_match.start(), end=marker_match.end())
                marker.set_uuid()

                if book is not None:
                    ref.book = book
                    marker.set_references([ref])

                    content = marker.replace_content_with_mask(content)
                    markers.append(marker)

                    for waiting in markers_waiting_for_book:
                        if len(waiting.references) == 1:
                            waiting.references[0].book = book
                            content = waiting.replace_content_with_mask(content)
                            markers.append(waiting)
                    markers_waiting_for_book = []
                else:
                    if marker_match.group("next_book") is not None:
                        marker.set_references([ref])
                        markers_waiting_for_book.append(marker)
                    else:
                        raise RefExError("next_book and book are None")

        if len(markers_waiting_for_book) > 0:
            logger.warning("Marker could not be assign to book: %s", markers_waiting_for_book)

        # Full law name references: § 40 des Verwaltungsverfahrensgesetzes
        full_name_suffixes = r"(?:gesetzes|gesetzbuches|gesetzbuch|gesetz|ordnung|verordnung|verfassung)"
        full_name_pattern = re.compile(
            section_sign
            + sect_space
            + r"(?P<sect>[0-9]+(?:\s?[a-z]?)).{0,80}?\s(?:des|der)\s(?:[a-zäüö][a-zäüöß]+\s)*"
            + r"(?P<book>[A-ZÄÜÖ][A-Za-zÄÜÖäüöß]+?"
            + full_name_suffixes
            + r")"
            + book_look_ahead
        )

        for marker_match in full_name_pattern.finditer(content):
            marker_text = marker_match.group(0)
            book = marker_match.group("book").strip().lower()

            # Strip genitive suffix: "gesetzes" → "gesetz", "gesetzbuches" → "gesetzbuch"
            if book.endswith("gesetzes") or book.endswith("gesetzbuches"):
                book = book[:-2]

            sect = marker_match.group("sect")
            ref = Ref(ref_type=RefType.LAW, book=book, section=Ref.clean_section(sect))

            marker = RefMarker(text=marker_text, start=marker_match.start(), end=marker_match.end())
            marker.set_uuid()
            marker.set_references([ref])

            markers.append(marker)
            content = marker.replace_content_with_mask(content)

        # TODO Art GG

        return markers

    def get_law_book_codes(self):
        """Book identifiers to build regex"""
        return self._law_book_codes

    @staticmethod
    def _build_law_book_ref_regex(law_book_codes):
        r"""
        Returns regex for law book part in reference markers.

        Currently returns a generic pattern matching common German law book abbreviations.
        TODO B7: use actual law_book_codes list for precision (behind feature flag).
        """
        if len(law_book_codes) < 1:
            raise RefExError("Cannot generate regex, law_book_codes are empty")

        logger.debug("Law book ref with %i books", len(law_book_codes))

        return r"([A-ZÄÜÖ][-ÄÜÖäüöA-Za-z]{,20})(V|G|O|B)(?:\s([XIV]{1,5}))?"

    # Keep old name as alias for backward compat
    def get_law_book_ref_regex(self, law_book_codes, optional=False, group_name=False, to_lower=False):
        if optional:
            raise ValueError("optional=True not supported")
        if group_name:
            raise ValueError("group_name=True not supported")
        return self._build_law_book_ref_regex(law_book_codes)

    def extract_law_ref_markers_with_context(self, content):
        """
        With context = citing law book is known

        § 343 der Zivilprozessordnung
        :param content:
        :return:
        """
        markers = []

        book_code = self.law_book_context
        # Normalize HTML entity for § (ported from legacy law.py)
        search_text = str(content).replace("&#167;", "§")

        def multi_sect(match):
            start = int(match.group(1))
            end = int(match.group(3)) + 1
            sects = []

            for sect in range(start, end):
                sects.append(str(sect))

            return sects

        def multi_book(match):
            start = int(match.group(1))
            end = int(match.group(3)) + 1
            return [book_code] * (end - start)

        patterns = [
            # §§ 664 bis 670
            {
                "pattern": re.compile("§§ ([0-9]+) (bis|und) ([0-9]+)"),
                "book": multi_book,
                "sect": multi_sect,
            },
            # Anlage 3
            {
                "pattern": re.compile("Anlage ([0-9]+)"),
                "book": lambda match: book_code,
                "sect": lambda match: f"anlage-{int(match.group(1))}",
            },
            # § 1
            {
                "pattern": re.compile(r"§ ([0-9]+)(?:\s(Abs\.|Absatz)\s([0-9]+))?(?:\sSatz\s([0-9]+))?"),
                "book": lambda match: book_code,
                "sect": lambda match: match.group(1),
            },
        ]

        for p in patterns:
            regex = p["pattern"]

            for ref_m in regex.finditer(search_text):
                ref_text = ref_m.group(0)

                ref_ids = []
                books = p["book"](ref_m)
                sects = p["sect"](ref_m)

                if not isinstance(books, str):
                    for key, book in enumerate(books):
                        ref_ids.append(Ref(ref_type=RefType.LAW, book=book, section=sects[key]))
                else:
                    ref_ids.append(Ref(ref_type=RefType.LAW, book=books, section=sects))

                ref = RefMarker(text=ref_text, start=ref_m.start(), end=ref_m.end())
                ref.set_uuid()
                ref.set_references(ref_ids)
                markers.append(ref)

                search_text = (
                    search_text[: ref_m.start()] + ("_" * (ref_m.end() - ref_m.start())) + search_text[ref_m.end() :]
                )

        return markers
