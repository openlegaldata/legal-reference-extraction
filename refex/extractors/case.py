import logging
import re
from typing import Tuple, List

import nltk

from refex.errors import RefExError, AmbiguousReferenceError
from refex.models import RefMarker, Ref, RefType

logger = logging.getLogger(__name__)


class CaseRefExtractorMixin(object):
    court_context = None

    def clean_text_for_tokenizer(self, text):
        """
        Remove elements from text that can make the tokenizer fail.

        :param text:
        :return:
        """
        def repl(m):
            return '_' * (len(m.group()))

        def repl2(m):
            # print(m.group(2))
            return m.group(1) + ('_' * (len(m.group(2)) + 1))

        # (...) and [...]
        text = re.sub(r'\((.*?)\)', repl, text)

        # Dates
        text = re.sub(r'(([0-9]+)\.([0-9]+)\.([0-9]+)|i\.S\.d\.)', repl, text)

        # Abbr.
        text = re.sub(r'(\s|\(|\[)([0-9]+|[IVX]+|[a-zA-Z]|sog|ca|Urt|Abs|Nr|lfd|vgl|Rn|Rspr|std|ff|bzw|Art)\.', repl2, text)

        # Schl.-Holst.
        text = re.sub(r'([a-z]+)\.-([a-z]+)\.', repl, text, flags=re.IGNORECASE)


        return text

    def get_court_name_regex(self):
        """
        Regular expression for finding court names

        :return: regex
        """
        # TODO Fetch from DB
        # TODO generate only once

        federal_courts = [
            'Bundesverfassungsgericht', 'BVerfG',
            'Bundesverwaltungsgericht', 'BVerwG',
            'Bundesgerichtshof', 'BGH',
            'Bundesarbeitsgericht', 'BAG',
            'Bundesfinanzhof', 'BFH',
            'Bundessozialgericht', 'BSG',
            'Bundespatentgericht', 'BPatG',
            'Truppendienstgericht Nord', 'TDG Nord',
            'Truppendienstgericht Süd', 'TDG Süd',
            'EUGH',
        ]
        states = [
            'Berlin',
            'Baden-Württemberg', 'BW',
            'Brandenburg', 'Brandenburgisches',
            'Bremen',
            'Hamburg',
            'Hessen',
            'Niedersachsen',
            'Hamburg',
            'Mecklenburg-Vorpommern',
            'Nordrhein-Westfalen', 'NRW',
            'Rheinland-Pfalz',
            'Saarland',
            'Sachsen',
            'Sachsen-Anhalt',
            'Schleswig-Holstein', 'Schl.-Holst.', 'SH',
            'Thüringen'
        ]
        state_courts = [
            'OVG',
            'VGH'
        ]
        cities = [
            'Baden-Baden',
            'Berlin-Brbg.'
            'Wedding',
            'Schleswig'
        ]
        city_courts = [
            'Amtsgericht', 'AG',
            'Landgericht', 'LG',
            'Oberlandesgericht', 'OLG',
            'OVG'
        ]

        pattern = None
        for court in federal_courts:
            if pattern is None:
                pattern = r'('
            else:
                pattern += '|'

            pattern += court

        for court in state_courts:
            for state in states:
                pattern += '|' + court + ' ' + state
                pattern += '|' + state + ' ' + court

        for c in city_courts:
            for s in cities:
                pattern += '|' + c + ' ' + s
                pattern += '|' + s + ' ' + c

        pattern += ')'

        # logger.debug('Court regex: %s' % pattern)

        return pattern

    def get_file_number_regex(self):
        return r'([0-9]+)\s([a-zA-Z]{,3})\s([0-9]+)/([0-9]+)'

    def extract_case_ref_markers(self, content: str) -> Tuple[str, List[RefMarker]]:
        """
        BVerwG, Urteil vom 20. Februar 2013, - 10 C 23.12 -
        BVerwG, Urteil vom 27. April 2010 - 10 C 5.09 -
        BVerfG, Beschluss vom 10.07.1989, - 2 BvR 502, 1000, 961/86 -
        BVerwG, Urteil vom 20.02.2013, - 10 C 23.12 -
        OVG Nordrhein-Westfalen, Urteil vom 21.2.2017, - 14 A 2316/16.A -
        OVG Nordrhein-Westfalen, Urteil vom 29.10.2012 – 2 A 723/11 -
        OVG NRW, Urteil vom 14.08.2013 – 1 A 1481/10, Rn. 81 –
        OVG Saarland, Urteil vom 2.2.2017, - 2 A 515/16 -
        OVG Rheinland-Pfalz, Urteil vom 16.12.2016, -1A 10922/16 -
        Bayrischer VGH, Urteil vom 12.12.16, - 21 B 16.30364
        OVG Nordrhein-Westfalen, Urteil vom 21.2.2017, - 14 A 2316/16.A -
        Bayrischer VGH, Urteil vom 12.12.2016, - 21 B 16.30372 -
        OVG Saarland, Urteil vom 2.2.2017, - 2 A 515/16 -
        OVG Rheinland-Pfalz, Urteil vom 16.12.2016, -1A 10922/16 -
        VG Minden, Urteil vom 22.12.2016, - 1 K 5137/16.A -
        VG Gießen, Urteil vom 23.11.2016, - 2 K 969/16.GI.A
        VG Düsseldorf, Urteil vom 24.1.2017, - 17 K 9400/16.A
        VG Köln, Beschluss vom 25.03.2013 – 23 L 287/12 -
        OVG Schleswig, Beschluss vom 20.07.2006 – 1 MB 13/06 -
        Schleswig-Holsteinisches Verwaltungsgericht, Urteil vom 05.082014 – 11 A 7/14, Rn. 37 –
        Entscheidung des Bundesverwaltungsgerichts vom 24.01.2012 (2 C 24/10)

        EuGH Urteil vom 25.07.2002 – C-459/99 -

        TODO all court codes + case types

        - look for (Entscheidung|Bechluss|Urteil)
        - +/- 50 chars
        - find VG|OVG|Verwaltungsgericht|BVerwG|...
        - find location
        - find file number - ... - or (...)

        TODO

        Sentence tokenzier
        - remove all "special endings" \s([0-9]+|[a-zA-Z]|sog|Abs)\.
        - remove all dates

        :param key:
        :param content:
        :return:
        """

        refs = []
        original = content
        text = content

        # print('Before = %s'  % text)

        # Clean up text; replacing all chars that can lead to wrong sentences
        text = self.clean_text_for_tokenizer(text)

        # TODO
        from nltk.tokenize.punkt import PunktParameters
        punkt_param = PunktParameters()
        abbreviation = ['1', 'e', 'i']
        punkt_param.abbrev_types = set(abbreviation)
        # tokenizer = PunktSentenceTokenizer(punkt_param)

        offset = 0
        marker_offset = 0

        for start, end in nltk.PunktSentenceTokenizer().span_tokenize(text):
            length = end - start
            sentence = text[start:end]
            original_sentence = original[start:end]

            matches = list(re.finditer(r'\((.*?)\)', original_sentence))

            logger.debug('Sentence (matches: %i): %s' % (len(matches), sentence))
            logger.debug('Sentence (orignal): %s' % (original_sentence))

            for m in matches:
                # pass
                # print('offset = %i, len = %i' % (offset, len(sentence)))
                #
                # print('MANGLED: ' + sentence)
                logger.debug('Full sentence // UNMANGLED: ' + original_sentence)

                # focus_all = original[start+m.start(1):start+m.end(1)].split(',')
                focus_all = original_sentence[m.start(1):m.end(1)].split(',')


                # print(m.group(1))
                logger.debug('In parenthesis = %s' % focus_all)

                # Split
                for focus in focus_all:

                    # Search for file number
                    fns_matches = list(re.finditer(self.get_file_number_regex(), focus))

                    if len(fns_matches) == 1:
                        fn = fns_matches[0].group(0)
                        pos = fns_matches[0].start(0)

                        logger.debug('File number found: %s' % fn)

                        # Find court
                        court_name = None
                        court_pos = 999999
                        court_matches = list(re.finditer(self.get_court_name_regex(), original_sentence))

                        if len(court_matches) == 1:
                            # Yeah everything is fine
                            court_name = court_matches[0].group(0)

                        elif len(court_matches) > 0:
                            # Multiple results, choose the one that is closest to file number
                            for cm in court_matches:
                                if court_name is None or abs(pos - cm.start()) < court_pos:
                                    court_name = cm.group(0)
                                    court_pos = abs(pos - cm.start())
                        else:
                            # no court found, guess by search query
                            # probably the court of the current case? test for "die kammer"
                            pass

                        # Find date
                        # TODO

                        logger.debug('Filename = %s' % fn)
                        logger.debug('Courtname = %s' % court_name)

                        ref_start = start + m.start(1) + pos
                        ref_end = ref_start + len(fn)

                        if court_name is None:

                            # raise )
                            # TODO Probably same court as current case (use court context)
                            logger.error(AmbiguousReferenceError('No court name found - FN: %s' % fn))
                            # logger.debug('Sentence: %s' % (fn, original_sentence)))
                            continue

                        ref_ids = [
                            Ref(ref_type=RefType.CASE, court=court_name, file_number=fn)  # TODO date field
                        ]
                        # TODO maintain order for case+law refs
                        marker = RefMarker(text=focus,
                                                  start=ref_start,
                                                  end=ref_end,
                                                  line=0)  # TODO line number
                        marker.set_uuid()
                        marker.set_references(ref_ids)

                        refs.append(
                            marker
                        )

                        content, marker_offset = marker.replace_content(content, marker_offset)

                        pass
                    elif len(fns_matches) > 1:
                        logger.warning('More file numbers found: %s' % fns_matches)

                        pass
                    else:
                        logger.debug('No file number found')

        return content, refs