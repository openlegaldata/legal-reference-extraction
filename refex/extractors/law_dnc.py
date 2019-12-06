import logging
import re
from typing import List

from refex.errors import RefExError
from refex.models import RefMarker, Ref, RefType

logger = logging.getLogger(__name__)


class DivideAndConquerLawRefExtractorMixin(object):
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

    # Used when reference has only section but now book
    # (citations within a law book to other sections, § 1 AB -> § 2 AB)
    law_book_context = None

    # Book identifiers (used to generate regular expression)
    law_book_codes = []
    default_law_book_codes = ['AsylG', 'BGB', 'GG', 'VwGO', 'GkG', 'stbstg', 'lbo', 'ZPO', 'LVwG', 'AGVwGO SH', 'BauGB',
                                'BauNVO', 'ZWStS', 'SbStG', 'StPO', 'TKG', 'SG', 'SGG', 'SGB X']

    # All text non-word symbols
    word_delimiter = '\s|\.|,|;|:|!|\?|\(|\)|\[|\]|"|\'|<|>|&'

    def extract_law_ref_markers(self, content: str, is_html: bool) -> List[RefMarker]:
        """

        The main extraction method. Takes input content and returns content with markers and list of extracted references.

        Divide and Conquer
        - only simple regex
        - replace matches with mask (_REF_) to avoid multiple matches

        :param content: Plain-text or even HTML
        :return: List of reference markers
        """

        if self.law_book_context is not None:
            # Extraction with context available is done in another method
            return self.extract_law_ref_markers_with_context(content)

        # Init
        markers = []

        # Replace special characters if working with html
        if is_html:
            sectionSign = '&#167;'
            self.word_delimiter = '\s|\.|,|;|:|!|\?|\(|\)|\[|\]|&#8221;|\&#8216;|\&#8217;|&#60;|&#62;|&#38;'
        else:
            sectionSign = '§'



        book_look_ahead = '(?=' + self.word_delimiter + ')'  # book code should be followed by a word separator, e.g. space.

        # Single ref
        book_pattern = self.get_law_book_ref_regex(self.get_law_book_codes())



        # Any content
        any_content = '(\s?([0-9]{1,5}(\.{,1})|[a-z]{1,2}|[IXV]{1,3}|Abs\.|Abs|Satz|Halbsatz|S\.|Nr|Nr\.|Alt|Alt\.|und|bis|,|;|\s))*'
        any_content = '([0-9]{1,5}|\.|[a-z]|[IXV]{1,3}|Abs\.|Abs|Satz|Halbsatz|S\.|Nr|Nr\.|Alt|Alt\.|und|bis|,|;|\s)*'


        multi_pattern = sectionSign + sectionSign + ' (\s|[0-9]+(\.{,1})|[a-z]|Abs\.|Abs|Satz|Halbsatz|S\.|Nr|Nr\.|Alt|Alt\.|f\.|ff\.|und|bis|\,|;|\s'+ book_pattern + ')+\s(' + book_pattern + ')' + book_look_ahead




        for marker_match in re.finditer(re.compile(multi_pattern), content):  # All matches
            marker_text = marker_match.group(0)
            refs = []
            refs_waiting_for_book = []

            # print('>> ' + marker_text)
            logger.debug('Multi Match with: %s' % marker_text)

            # Books by position in text
            book_positions = {}  # Can we ensure that book_position is in order?
            for book_match in re.finditer(book_pattern, marker_text):
                book_positions[book_match.start()] = book_match.group(0)

            # We cannot work without knowing the book
            if len(book_positions) < 0:
                logger.error('No book found in marker text: %s' % marker_text)
                continue

            # Extract references from marker text
            # - find for <separator §§|,|..> + <section>
            # - ignore Abs, Nr, ...
            # - corresponding book is the closest to right
            a = '([0-9]+)\s(?=bis|und)'
            b = '([0-9]+)\s?[a-z]'
            c = '([0-9]+)'
            pattern = '(?P<sep>' + sectionSign + sectionSign + '|,|;|und|bis)\s?(?P<sect>(' + a + '|' + b + '|' + c + '))'


            for ref_match in re.finditer(re.compile(pattern), marker_text):
                sect = ref_match.group('sect')

                logger.debug('Found ref: %s' % ref_match.group())

                if len(book_positions) == 1:
                    book = next(iter(book_positions.values()))
                else:
                    book = None
                    pos = ref_match.start()

                    for bp in book_positions:
                        if bp > pos:
                            # Take the first book that is right to section position
                            book = book_positions[bp]
                            break

                if book is None:
                    logger.error('No book after reference found: %s - %s' % (ref_match.group(0), marker_text))
                    continue

                # Check for 'between' (range sections)
                if ref_match.group('sep') == 'bis' and len(refs) > 0:
                    from_sect = refs[-1].section  # last section

                    # Both sections should be integers (no a-z sections)
                    if sect.isdigit() and from_sect.isdigit():
                        for between_sect in range(int(from_sect) + 1, int(sect)):
                            # Add to queue
                            refs.append(Ref.init_law(book=book, section=str(between_sect)))

                refs.append(Ref.init_law(book=book, section=sect))

            # Prepare marker
            marker = RefMarker(text=marker_text,
                               start=marker_match.start(),
                               end=marker_match.end())
            marker.set_uuid()
            marker.set_references(refs)

            # Check if actual references were found in marker text
            if len(refs) > 0:
                markers.append(marker)

                # Update content to avoid double matching
                content = marker.replace_content_with_mask(content)
            else:
                logger.warning('No references found in marker: %s ' % marker_text)


        # Single refs
        sect_pattern = '(?P<sect>([0-9]+)(\s?[a-z]?))'
        patterns = [
            # § 3 BGB, § 3d BGB, § 83 d BGB
            sectionSign + ' ' + sect_pattern + ' (?P<book>' + book_pattern + ')' + book_look_ahead,
            # Abs OR Nr
            # § 42 Abs. 1 Alt. 1 VwGO
            sectionSign + ' ' + sect_pattern + ' Abs. ([0-9]+) Alt. ([0-9]+) (?P<book>' + book_pattern + ')' + book_look_ahead,
            sectionSign + ' (?P<sect>([0-9]+)(\s?[a-z]?)) ' + any_content + ' (?P<book>(' + book_pattern + '))' + book_look_ahead,
            sectionSign + ' (?P<sect>([0-9]+)(\s?[a-z]?)) ' + any_content + ' (?P<next_book>(i\.V\.m\.|iVm))' + book_look_ahead,

        ]

        markers_waiting_for_book = []  # type: List[RefMarker]

        for pattern in patterns:  # Iterate over all patterns

            # logger.debug('Pattern: %s' % pattern)

            for marker_match in re.finditer(re.compile(pattern), content):  # All matches
                marker_text = marker_match.group(0)
                if 'book' in marker_match.groupdict():
                    book = Ref.clean_book(marker_match.group('book'))
                else:
                    book = None

                ref = Ref.init_law(section=marker_match.group('sect'), book=None)

                marker = RefMarker(text=marker_text,
                                   start=marker_match.start(),
                                   end=marker_match.end())
                marker.set_uuid()
                # marker.uuid = 's'

                # Has this marker a book
                if book is not None:
                    ref.book = book

                    marker.set_references([ref])

                    # Update content to avoid double matching
                    content = marker.replace_content_with_mask(content)

                    markers.append(marker)

                    # Set to waiting markers
                    for waiting in markers_waiting_for_book:
                        if len(waiting.references) == 1:
                            waiting.references[0].book = book

                            content = waiting.replace_content_with_mask(content)

                            markers.append(waiting)
                    markers_waiting_for_book = []
                else:
                    if marker_match.group('next_book') is not None:
                        marker.set_references([ref])
                        markers_waiting_for_book.append(marker)
                    else:
                        raise RefExError('next_book and book are None')

        if len(markers_waiting_for_book) > 0:
            logger.warning('Marker could not be assign to book: %s' % markers_waiting_for_book)

        # TODO Art GG

        return markers

    def get_law_book_codes(self):
        """Book identifiers to build regex"""
        if self.law_book_codes is None:
            self.law_book_codes = []

        if len(self.law_book_codes) < 1:
            # Extend with pre-defined codes
            self.law_book_codes.extend(self.default_law_book_codes)

        return self.law_book_codes

    def get_law_book_ref_regex(self, law_book_codes, optional=False, group_name=False, to_lower=False):
        """
        Returns regex for law book part in reference markers (OR list).

        TODO book codes should be ordered by reverse string length (SG|SGB X) -> (SGB X|SG), SGG
        - Solution: book code needs to be followed by (\s|\.|,|;|:|"|'|\)|])

        TODO Add refex for ending [A-Z][A-Za-z](V|G|O)
        - start with capital letter
        - end with V, G or O

        Example:
            - codes: ['ab', 'cd', 'de']
            - output: ab|cd|de

        """

        # return '[a-zA-Z]'

        if len(law_book_codes) < 1:
            raise RefExError('Cannot generate regex, law_book_codes are empty')

        if optional:
            raise ValueError('optional=True not supported')

        if group_name:
            raise ValueError('group_name=True not supported')

        logger.debug('Law book ref with %i books' % len(law_book_codes))

        # return '|'.join([code.lower() if to_lower else code for code in law_book_codes])

        # alternative regex:
        # start with capital char
        # optional, max length chars
        # ends with V,G,O or B
        # optional space + roman numbers (e.g. SGB IX)
        return '([A-ZÄÜÖ][-ÄÜÖäüöA-Za-z]{,20})(V|G|O|B)(?:\s([XIV]{1,5}))?'

    def extract_law_ref_markers_with_context(self, content):
        """
        With context = citing law book is known

        § 343 der Zivilprozessordnung
        :param content:
        :return:
        """
        markers = []

        book_code = self.law_book_context
        # content = content.replace('&#167;', '§')
        search_text = str(content)

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
                'pattern': '§§ ([0-9]+) (bis|und) ([0-9]+)',
                'book': multi_book,
                'sect': multi_sect
            },
            # Anlage 3
            {
                'pattern': 'Anlage ([0-9]+)',
                'book': lambda match: book_code,
                'sect': lambda match: 'anlage-%i' % int(match.group(1))
            },

            # § 1
            {
                'pattern': '§ ([0-9]+)(?:\s(Abs\.|Absatz)\s([0-9]+))?(?:\sSatz\s([0-9]+))?',
                'book': lambda match: book_code,
                'sect': lambda match: match.group(1)
            },

        ]

        for p in patterns:
            regex = p['pattern']

            res = re.finditer(regex, search_text)  # flags

            for ref_m in res:
                ref_text = ref_m.group(0)

                # Build ref with lambda functions
                ref_ids = []
                books = p['book'](ref_m)
                sects = p['sect'](ref_m)

                # Handle multiple ref ids in a single marker
                if not isinstance(books, str):
                    for key, book in enumerate(books):
                        ref_ids.append(Ref(ref_type=RefType.LAW, book=book, section=sects[key]))

                else:
                    ref_ids.append(Ref(ref_type=RefType.LAW, book=books, section=sects))

                ref = RefMarker(text=ref_text, start=ref_m.start(), end=ref_m.end())
                ref.set_uuid()
                ref.set_references(ref_ids)
                markers.append(ref)

                # Remove from search content to avoid duplicate matches
                search_text = search_text[:ref_m.start()] + ('_' * (ref_m.end() - ref_m.start())) \
                              + search_text[ref_m.end():]
                # print('-------')

        # Sort by start and replace markers
        # markers.sort(key=lambda r: r.start, reverse=False)
        # marker_offset = 0
        # for key, ref in enumerate(markers):
        #     content, marker_offset = ref.replace_content(content, marker_offset)

        return markers
