import logging
import re
from typing import Tuple, List

from refex.errors import RefExError
from refex.models import RefMarker, Ref, RefType

logger = logging.getLogger(__name__)


class LawRefExtractorMixin(object):
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
                                'BauNVO', 'ZWStS', 'SbStG', 'StPO', 'TKG']

    def extract_law_ref_markers(self, content: str) -> Tuple[str, List[RefMarker]]:
        """

        The main extraction method. Takes input content and returns content with markers and list of extracted references.

        :param content: Plain-text or even HTML
        :return: Content with reference markers, List of reference markers
        """

        logger.debug('Extracting from: %s' % content)

        if self.law_book_context is not None:
            # Extraction with context available is done in another method
            return self.extract_law_ref_markers_with_context(content)

        # Init
        markers = []
        marker_offset = 0

        # Handle each match separately
        for marker_match in re.finditer(self.get_law_ref_regex(self.get_law_book_codes()), content):

            marker_text = str(marker_match.group(0)).strip()
            references = []

            # Handle single and multi refs separately
            if re.match(r'^(Art(\.{,1})|§)\s', marker_text):
                references = self.handle_single_law_ref(self.get_law_book_codes(), marker_text, references)

            elif re.match(r'^§§\s', marker_text):
                references = self.handle_multiple_law_refs(self.get_law_book_codes(), marker_text, references)

            else:
                raise RefExError('Unsupported ref beginning: %s' % marker_text)

            marker = RefMarker(text=marker_text,
                               start=marker_match.start(),
                               end=marker_match.end(),
                               line=0)  # TODO
            marker.set_uuid()
            marker.set_references(references)

            markers.append(marker)
            content, marker_offset = marker.replace_content(content, marker_offset)

        return content, markers

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

        return '|'.join([code.lower() if to_lower else code for code in law_book_codes])

    def get_law_ref_regex(self, law_book_codes) -> str:
        """
        Based on a list of law books we build a regex that matches reference markers.

        General regex, actual extraction is done with either single or multiple regex.

        Useful tools:
        - http://regexr.com/
        - https://www.debuggex.com/

        Regex Notes:
        - (a|b|c) == a OR b OR c
        - ? = optional
        - {1,2} == length of 1 or 2

        :return: regular expression
        """

        regex = r'(§|§§|Art(\.{,1}))\s'
        regex += '(\s|[0-9]+(\.{,1})|[a-z]|Abs\.|Abs|Satz|Halbsatz|S\.|Nr|Nr\.|Alt|Alt\.|f\.|ff\.|und|bis|\,|;|\s' \
                 + self.get_law_book_ref_regex(law_book_codes, optional=False, group_name=False) + ')+'
        regex += '\s(' + self.get_law_book_ref_regex(law_book_codes, optional=False, group_name=False) + ')'

        logger.debug('Regex: %s' % regex)

        return regex

    def get_law_ref_match_single(self, law_book_codes, ref_str):
        # Single ref
        regex_a = '(Art(\.{,1})|§)\s'
        regex_a += '((?P<sect>[0-9]+)\s?(?P<sect_az>[a-z])?)'                # f. ff.
        regex_a += '(\s?([0-9]+(\.{,1})|[a-z]{1,2}|Abs\.|Abs|Satz|Halbsatz|S\.|Nr|Nr\.|Alt|Alt\.|und|bis|,|;|\s))*'
        # regex_a += '\s?(?:(Abs.|Abs)\s?(?:[0-9]{1,2})\s?((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*)?'
        # regex_a += '\s?((Satz|S\.)\s[0-9]{1,2})?'
        # regex_a += '\s?(((Nr|Nr\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'
        # regex_a += '\s?(((Alt|Alt\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'

        regex_a += '\s(?P<book>' + self.get_law_book_ref_regex(law_book_codes, optional=False) + ')'

        return re.search(regex_a, ref_str)

    def get_law_ref_match_multi(self, law_book_codes, ref_str):
        pattern = r'(?P<delimiter>§§|,|;|und|bis)\s?'
        pattern += '((?P<sect>[0-9]+)\s?'
        # pattern += '(?P<sect_az>[a-z])?)'
        # (?!.*?bis).*([a-z]).*)
        # pattern += '(?P<sect_az>(?!.*?bis).*([a-z]).*)?)'
        # (?!(moscow|outside))
        # pattern += '(?P<sect_az>(([a-z])(?!(und|bis))))?)'
        pattern += '((?P<sect_az>[a-z])(\s|,|;))?)'  # Use \s|, to avoid matching "bis" and "Abs", ...

        pattern += '(\s?(Abs\.|Abs)\s?([0-9]+))*'
        pattern += '(\s?(S\.|Satz|Halbsatz)\s?([0-9]+))*'

        # pattern += '(?:\s(Nr\.|Nr)\s([0-9]+))'
        # pattern += '(?:\s(S\.|Satz)\s([0-9]+))'

        # pattern += '(?:\s(f\.|ff\.))?'
        pattern += '(\s?(f\.|ff\.))*'

        # pattern += '(\s(Abs.|Abs)\s?([0-9]+)((,|und|bis)\s([0-9]+))*)*'
        # pattern += '\s?(?:(Abs.|Abs)\s?(?:[0-9]{1,2})\s?((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*)?'

        # logger.debug('Multi ref regex: %s' % pattern)


        pattern += '\s?(?:(?P<book>' + self.get_law_book_ref_regex(law_book_codes) + '))?'

        # print('MULTI: ' + ref_str)
        # print(pattern)
        #
        logger.debug('Multi ref regex: %s' % pattern)

        return re.finditer(pattern, ref_str)

    def handle_multiple_law_refs(self, law_book_codes, ref_str, law_ids) -> List[Ref]:
        # Search for multiple refs
        matches = self.get_law_ref_match_multi(law_book_codes, ref_str)

        refs_tmp = []
        prev_sect = None
        prev_book = None

        logger.debug('Multi refs found in: %s' % ref_str)

        # Loop over all results
        for match in matches:

            # If book is not set, use __placeholder__ and replace later
            if match.group('book') is not None:
                book = match.group('book').lower()
            else:
                book = '__book__'

            # Section must exist
            if match.group('sect') is not None:
                sect = str(match.group('sect'))
            else:
                raise RefExError('Ref sect is not set')

            if match.group('sect_az') is not None:
                sect += match.group('sect_az').lower()

            ref = Ref(ref_type=RefType.LAW, book=book, section=sect)

            logger.debug('Ref found: %s (%s)' % (ref, match.group(0)))

            # Check for section ranges
            if match.group('delimiter') == 'bis':
                logger.debug('Handle section range - Add ids from ' + prev_sect + ' to ' + sect)
                # TODO how to handle az sects
                prev_sect = re.sub('[^0-9]', '', prev_sect)
                sect = re.sub('[^0-9]', '', sect)

                for between_sect in range(int(prev_sect)+1, int(sect)):
                    # print(between_sect)

                    refs_tmp.append(Ref(ref_type=RefType.LAW, book=prev_book, section=str(between_sect)))
            else:
                prev_sect = sect
                prev_book = book

            refs_tmp.append(ref)

        # law_ids.append('multi = ' + ref_str)
        # handle __book__
        logger.debug('All law ids found: %s' % refs_tmp)

        refs_tmp.reverse()
        book = None
        for id_tmp in refs_tmp:
            if id_tmp.book != '__book__':
                book = id_tmp.book
            elif book is not None:
                id_tmp.book = book
            else:
                raise RefExError('Cannot determine law book (Should never happen): %s' % ref_str)

            law_ids.append(id_tmp)

        return law_ids

    def handle_single_law_ref(self, law_book_codes, ref_str, law_ids):
        logger.debug('Single ref found in: %s' % ref_str)

        # Single ref
        mm = self.get_law_ref_match_single(law_book_codes, ref_str)

        # Find book and section (only single result possible)
        if mm is not None:
            # mm.groupdict()

            if mm.group('book') is not None:
                # Found book
                book = mm.group('book').lower()
            else:
                raise RefExError('Ref book is not set: %s ' % ref_str)

            if mm.group('sect') is not None:
                # Found section
                sect = str(mm.group('sect'))
            else:
                raise RefExError('Ref sect is not set')

            if mm.group('sect_az') is not None:
                # Found section addon
                sect += mm.group('sect_az').lower()

            law_id = Ref(ref_type=RefType.LAW, book=book, section=sect)

            logger.debug('Law ID: %s' % law_id)

            law_ids.append(law_id)
        else:
            # law_ids.append({'book': 'not matched', 'sect': 'NOT MATCHED (single) %s ' % ref_str})
            logger.warning('Law ID could not be matched: %s' % ref_str)

        return law_ids


    def extract_law_ref_markers_with_context(self, content):
        """
        With context = citing law book is known

        § 343 der Zivilprozessordnung
        :param content:
        :return:
        """
        markers = []

        book_code = self.law_book_context
        content = content.replace('&#167;', '§')
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
        markers.sort(key=lambda r: r.start, reverse=False)
        marker_offset = 0
        for key, ref in enumerate(markers):
            content, marker_offset = ref.replace_content(content, marker_offset)

        return content, markers
