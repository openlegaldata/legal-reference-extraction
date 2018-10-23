import logging
import re
from typing import Tuple, List

from refex.errors import RefExError
from refex.models import RefMarker, Ref, RefType

logger = logging.getLogger(__name__)


class LawRefExtractorMixin(object):
    law_book_context = None
    law_book_codes = ['AsylG', 'VwGO', 'GkG', 'stbstg', 'lbo', 'ZPO', 'LVwG', 'AGVwGO SH', 'BauGB',
                                'BauNVO', 'ZWStS', 'SbStG', 'StPO', 'TKG']

    def test_ref_extraction(self, value):
        # (.+?)\\[/ref\\]
        value = re.sub(r'\[ref=([0-9]+)\](.+?)\[/ref\]', '______', value)

        if re.search(r'§', value, re.IGNORECASE):
            return value
        else:
            return None

    def get_law_book_codes(self):
        if self.law_book_codes is None:
            self.law_book_codes = []

        if len(self.law_book_codes) < 1:
            # Extend with pre-defined codes
            self.law_book_codes.extend(['AsylG', 'VwGO', 'GkG', 'stbstg', 'lbo', 'ZPO', 'LVwG', 'AGVwGO SH', 'BauGB',
                                       'BauNVO', 'ZWStS', 'SbStG', 'StPO', 'TKG'])

        return self.law_book_codes

    def get_law_book_ref_regex(self, optional=True, group_name=True, lower=False):
        """Returns regex for law book part in reference markers"""

        # law_book_codes = list(json.loads(open(self.law_book_codes_path).read()).keys())
        law_book_codes = self.get_law_book_codes()

        if len(law_book_codes) < 1:
            raise RefExError('Cannot generate regex, law_book_codes are empty')

        law_book_regex = None
        for code in law_book_codes:
            if lower:
                code = code.lower()

            if law_book_regex is None:
                # if optional:
                #     law_book_regex = '('
                # else:
                #     law_book_regex = '('
                law_book_regex = ''

                # if group_name:
                #     law_book_regex += '?P<book>'

                law_book_regex += code
            else:
                law_book_regex += '|' + code
                # law_book_regex += ')'

                # if optional:
                # law_book_regex += '?'

        return law_book_regex

    def get_law_ref_regex(self):

        # TODO Regex builder tool? http://regexr.com/
        # https://www.debuggex.com/
        # ((,|und)\s*((?P<nos>[0-9]+)+)*
        # regex += '(\s?([0-9]+|[a-z]{1,2}|Abs\.|Abs|Satz|S\.|Nr|Nr\.|Alt|Alt\.|f\.|ff\.|und|bis|\,|'\
        #regex = r'(§|§§|Art.) (?P<sect>[0-9]+)\s?(?P<sect_az>[a-z]*)\s?(?:Abs.\s?(?:[0-9]{1,2})|Abs\s?(?:[0-9]{1,2}))?\s?(?:Satz\s[0-9]{1,2})?\s' + law_book_regex
        regex = r'(§|§§|Art\.)\s'
        regex += '(\s|[0-9]+|[a-z]|Abs\.|Abs|Satz|S\.|Nr|Nr\.|Alt|Alt\.|f\.|ff\.|und|bis|\,|' \
                 + self.get_law_book_ref_regex(optional=False, group_name=False) + ')+'
        regex += '\s(' + self.get_law_book_ref_regex(optional=False, group_name=False) + ')'

        regex_abs = '((Abs.|Abs)\s?([0-9]+)((,|und|bis)\s([0-9]+))*)*'

        regex_a = '(([0-9]+)\s?([a-z])?)'
        regex_a += '((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*'
        # f. ff.
        regex_a += '\s?((Abs.|Abs)\s?([0-9]+))*'
        # regex_a += '\s?(?:(Abs.|Abs)\s?(?:[0-9]{1,2})\s?((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*)?'
        # regex_a += '\s?((Satz|S\.)\s[0-9]{1,2})?'
        # regex_a += '\s?(((Nr|Nr\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'
        # regex_a += '\s?(((Alt|Alt\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'

        regex_a += '\s'
        regex_a += '(' + self.get_law_book_ref_regex(optional=True, group_name=False) + ')'

        # regex += regex_a
        # regex += '(\s?(,|und)\s' + regex_a + ')*'
        #
        # logger.debug('Law Regex=%s' % regex)

        return regex

    def get_law_ref_match_single(self, ref_str):
        # Single ref
        regex_a = '(Art\.|§)\s'
        regex_a += '((?P<sect>[0-9]+)\s?(?P<sect_az>[a-z])?)'                # f. ff.
        regex_a += '(\s?([0-9]+|[a-z]{1,2}|Abs\.|Abs|Satz|S\.|Nr|Nr\.|Alt|Alt\.|und|bis|,))*'
        # regex_a += '\s?(?:(Abs.|Abs)\s?(?:[0-9]{1,2})\s?((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*)?'
        # regex_a += '\s?((Satz|S\.)\s[0-9]{1,2})?'
        # regex_a += '\s?(((Nr|Nr\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'
        # regex_a += '\s?(((Alt|Alt\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'

        regex_a += '\s(?P<book>' + self.get_law_book_ref_regex(optional=False) + ')'

        return re.search(regex_a, ref_str)

    def get_law_ref_match_multi(self, ref_str):
        pattern = r'(?P<delimiter>§§|,|und|bis)\s?'
        pattern += '((?P<sect>[0-9]+)\s?'
        # pattern += '(?P<sect_az>[a-z])?)'
        # (?!.*?bis).*([a-z]).*)
        # pattern += '(?P<sect_az>(?!.*?bis).*([a-z]).*)?)'
        # (?!(moscow|outside))
        # pattern += '(?P<sect_az>(([a-z])(?!(und|bis))))?)'
        pattern += '((?P<sect_az>[a-z])(\s|,))?)'  # Use \s|, to avoid matching "bis" and "Abs", ...

        pattern += '(\s?(Abs\.|Abs)\s?([0-9]+))*'
        pattern += '(\s?(S\.|Satz)\s?([0-9]+))*'

        # pattern += '(?:\s(Nr\.|Nr)\s([0-9]+))'
        # pattern += '(?:\s(S\.|Satz)\s([0-9]+))'

        # pattern += '(?:\s(f\.|ff\.))?'
        pattern += '(\s?(f\.|ff\.))*'

        # pattern += '(\s(Abs.|Abs)\s?([0-9]+)((,|und|bis)\s([0-9]+))*)*'
        # pattern += '\s?(?:(Abs.|Abs)\s?(?:[0-9]{1,2})\s?((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*)?'

        pattern += '\s?(?:(?P<book>' + self.get_law_book_ref_regex() + '))?'

        # print('MULTI: ' + ref_str)
        # print(pattern)

        # logger.debug('Multi ref regex: %s' % pattern)

        return re.finditer(pattern, ref_str)

    def get_law_id_from_match(self, match):
        # print(match.groups())

        return 'ecli://de/%s/%s%s' % (
            match.group('book').lower(),
            int(match.group('sect')),
            match.group('sect_az').lower()
        )

    def extract_law_ref_markers(self, content: str) -> Tuple[str, List[RefMarker]]:
        """
        § 3d AsylG
        § 123 VwGO
        §§ 3, 3b AsylG
        § 77 Abs. 1 Satz 1, 1. Halbsatz AsylG
        § 3 Abs. 1 AsylG
        § 77 Abs. 2 AsylG
        § 113 Abs. 5 Satz 1 VwGO
        § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG
        § 3a Abs. 1 und 2 AsylG
        §§ 154 Abs. 1 VwGO
        § 83 b AsylG
        § 167 VwGO iVm §§ 708 Nr. 11, 711 ZPO
        § 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO
        §§ 167 Abs. 2 VwGO, 708 Nr. 11, 711 ZPO
        §§ 52 Abs. 1; 53 Abs. 2 Nr. 1; 63 Abs. 2 GKG
        § 6 Abs. 5 Satz 1 LBO
        §§ 80 a Abs. 3, 80 Abs. 5 VwGO
        § 1 Satz 2 SbStG
        § 2 ZWStS
        § 6 Abs. 2 S. 2 ZWStS

        TODO all law-book jurabk

        :param referenced_by:
        :param key:
        :link https://www.easy-coding.de/Thread/5536-RegExp-f%C3%BCr-Gesetze/

        :param content:
        :return:
        """
        # TODO with context law book -> see old code
        logger.debug('Extracting law references')

        if self.law_book_context is not None:
            return self.extract_law_ref_markers_with_context(content)

        markers = []
        results = list(re.finditer(self.get_law_ref_regex(), content))
        marker_offset = 0

        logger.debug('Current content value: %s' % content)
        logger.debug('Law refs found: %i' % len(results))

        for ref_m in results:

            ref_str = str(ref_m.group(0)).strip()
            law_ids = []

            # Handle single and multi refs separately
            if re.match(r'^(Art\.|§)\s', ref_str):
                law_ids = self.handle_single_law_ref(ref_str, law_ids)

            elif re.match(r'^§§\s', ref_str):
                law_ids = self.handle_multiple_law_refs(ref_str, law_ids)

            else:
                raise RefExError('Unsupported ref beginning: %s' % ref_str)

            marker = RefMarker(text=ref_str,
                            start=ref_m.start(),
                            end=ref_m.end(),
                            line=0)  # TODO
            marker.set_uuid()
            marker.set_references(law_ids)

            markers.append(marker)
            content, marker_offset = marker.replace_content(content, marker_offset)

        return content, markers

    def handle_multiple_law_refs(self, ref_str, law_ids):
        # Search for multiple refs
        mms = self.get_law_ref_match_multi(ref_str)

        refs_tmp = []
        prev_sect = None
        prev_book = None

        logger.debug('Multi refs found in: %s' % ref_str)

        # Loop over all results
        for m in mms:

            # If book is not set, use __placeholder__ and replace later
            if m.group('book') is not None:
                book = m.group('book').lower()
            else:
                book = '__book__'

            # Section must exist
            if m.group('sect') is not None:
                sect = str(m.group('sect'))
            else:
                raise RefExError('Ref sect is not set')

            if m.group('sect_az') is not None:
                sect += m.group('sect_az').lower()

            ref = Ref(ref_type=RefType.LAW, book=book, section=sect)

            logger.debug('Law ID found: %s' % ref)

            # Check for section ranges
            if m.group('delimiter') == 'bis':
                logger.debug('Handle section range - Add ids from ' + prev_sect + ' to ' + sect)
                # TODO how to handle az sects
                prev_sect = re.sub('[^0-9]', '', prev_sect)
                sect = re.sub('[^0-9]', '', sect)

                for between_sect in range(int(prev_sect)+1, int(sect)):
                    # print(between_sect)

                    refs_tmp.append(Ref(ref_type=RefType.LAW, book=prev_book, section=between_sect))
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

    def handle_single_law_ref(self, ref_str, law_ids):
        logger.debug('Single ref found in: %s' % ref_str)

        # Single ref
        mm = self.get_law_ref_match_single(ref_str)

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
        TODO
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
                sects.append(sect)

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
