import collections
import logging
import os
import re
from typing import List, Set, Match

from refex.models import RefMarker, Ref, RefType

logger = logging.getLogger(__name__)


class CaseRefExtractorMixin(object):
    court_context = None
    codes = [
        'Sa',
    ]

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
            'VGH',
            'LSG',
        ]
        cities = [
            'Baden-Baden',
            'Berlin-Brbg.'
            'Wedding',
            'Schleswig',
            'Koblenz',
        ]
        city_courts = [
            'Amtsgericht', 'AG',
            'Landgericht', 'LG',
            'Oberlandesgericht', 'OLG',
            'OVG'
        ]

        options = []

        for court in federal_courts:
            options.append(court)

        for court in state_courts:
            for state in states:
                options.append(court + ' ' + state)
                options.append(state + ' ' + court)

        for c in city_courts:
            for s in cities:
                options.append(c + ' ' + s)
                options.append(s + ' ' + c)
        # logger.debug('Court regex: %s' % pattern)

        return r'(?P<court>' + ('|'.join(options)) + ')(\s|\.|;|,|:|\))'

    def get_file_number_regex(self):
        """
        Examples:

        1 O 137/15
        Au 5 K 17.31263

        <chamber> <code> <number> / <year>

        - chamber: zuständige Richter bzw. Spruchkörper (arabic or roman numbers)
        - code: Registerzeichen
        - number: laufende Nummer (numeric only)
        - separater: / or ,
        - year: Eingangsjahr (numeric, length = 2)

        Note: Bavaria has a different order - <year>.<number>

        <chamber> <code> <year>.<number>

        :return:
        """

        # |' + ('|'.join(self.get_codes())) + ')' \

        pattern = r'(?P<chamber>([0-9]+)[a-z]?|([IVX]+))' \
            + '\s' \
            + '(?P<code>[A-Za-z]{1,6})' \
            + '(\s\(([A-Za-z]{1,6})\))?' \
            + '(\s([A-Za-z]{1,6}))?' \
            + '\s' \
            + '(?P<number>[0-9]{1,6})' \
            + '\/' \
            + '(?P<year>[0-9]{2})'

        return pattern

    def extract_case_ref_markers(self, content: str) -> List[RefMarker]:
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
        marker_offset = 0

        # TODO More intelligent by search only in sentences.

        # Find all file numbers
        for match in re.finditer(self.get_file_number_regex(), content):  # type: Match
            court = None

            # Search in surroundings for court names
            for diff in [100, 200, 500]:
                # TODO maybe search left first, then to the right

                start = max(0, match.start(0) - diff)
                end = min(len(content), match.end(0) + diff)
                surrounding = content[start:end]

                print('Surroundings: %s'  % content[start:end])

                # File number position in surroundings
                fn_pos = match.start(0) - start
                candidates = collections.OrderedDict()

                for court_match in re.finditer(self.get_court_name_regex(), surrounding):
                    candidate_pos = round((court_match.start(0) + court_match.end(0)) / 2)  # Position = center
                    candidate_dist = abs(fn_pos - candidate_pos)  # Distance to file number

                    print('-- Candidate: %s / pos: %i / dist: %i' % (court_match.group(0), candidate_pos, candidate_dist))

                    if candidate_dist not in candidates:
                        candidates[candidate_dist] = court_match
                    else:
                        logger.warning('Court candidate with same distance exist already: %s' % court_match)

                # Court is the candidate with smallest distance to file number
                if len(candidates) > 0:
                    court = next(iter(candidates.values())).group('court')
                    # Stop searching if court was found with this range
                    break

            if court is None:
                court = ''

            file_number = match.group(0)
            ref_ids = [
                Ref(ref_type=RefType.CASE, court=court, file_number=file_number)  # TODO date field
            ]
            # TODO maintain order for case+law refs
            marker = RefMarker(text=file_number,
                               start=match.start(0),
                               end=match.end(0),
                               line=0)  # TODO line number
            marker.set_uuid()
            marker.set_references(ref_ids)

            refs.append(
                marker
            )

            # print(match.start(0))

        return refs


    def get_codes(self) -> Set[str]:
        """Codes used in file numbers"""
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        code_path = os.path.join(data_dir, 'file_number_codes.csv')

        with open(code_path, 'r') as f:
            codes = []
            for line in f.readlines():
                cols = line.strip().split(',', 2)

                # Strip parenthesis
                code = re.sub(r'\((.*?)\)', '', cols[0])

                codes.append(code)

            return set(codes)
