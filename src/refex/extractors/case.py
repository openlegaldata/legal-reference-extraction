import collections
import importlib.resources
import logging
import re

from refex.models import Ref, RefMarker, RefType

logger = logging.getLogger(__name__)


class CaseRefExtractorMixin:
    court_context = None
    codes = [
        "Sa",
    ]

    def clean_text_for_tokenizer(self, text):
        """
        Remove elements from text that can make the tokenizer fail.

        :param text:
        :return:
        """

        def repl(m):
            return "_" * (len(m.group()))

        def repl2(m):
            # print(m.group(2))
            return m.group(1) + ("_" * (len(m.group(2)) + 1))

        # (...) and [...]
        text = re.sub(r"\((.*?)\)", repl, text)

        # Dates
        text = re.sub(r"(([0-9]+)\.([0-9]+)\.([0-9]+)|i\.S\.d\.)", repl, text)

        # Abbr.
        text = re.sub(
            r"(\s|\(|\[)([0-9]+|[IVX]+|[a-zA-Z]|sog|ca|Urt|Abs|Nr|lfd|vgl|Rn|Rspr|std|ff|bzw|Art)\.",
            repl2,
            text,
        )

        # Schl.-Holst.
        text = re.sub(r"([a-z]+)\.-([a-z]+)\.", repl, text, flags=re.IGNORECASE)

        return text

    def get_court_name_regex(self):
        """
        Regular expression for finding court names

        :return: regex
        """
        # TODO Fetch from DB
        # TODO generate only once

        federal_courts = [
            "Bundesverfassungsgericht",
            "BVerfG",
            "Bundesverwaltungsgericht",
            "BVerwG",
            "Bundesgerichtshof",
            "BGH",
            "Bundesarbeitsgericht",
            "BAG",
            "Bundesfinanzhof",
            "BFH",
            "Bundessozialgericht",
            "BSG",
            "Bundespatentgericht",
            "BPatG",
            "Truppendienstgericht Nord",
            "TDG Nord",
            "Truppendienstgericht Süd",
            "TDG Süd",
            "EUGH",
            "Truppendienstgericht S&#252;d",
            "TDG S&#252;d",
        ]
        states = [
            "Berlin",
            "Baden-Württemberg",
            "BW",
            "Baden-W&#252;rttemberg",
            "Brandenburg",
            "Brandenburgisches",
            "Bremen",
            "Hamburg",
            "Hessen",
            "Niedersachsen",
            "Hamburg",
            "Mecklenburg-Vorpommern",
            "Nordrhein-Westfalen",
            "NRW",
            "Rheinland-Pfalz",
            "Saarland",
            "Sachsen",
            "Sachsen-Anhalt",
            "Schleswig-Holstein",
            "Schl.-Holst.",
            "SH",
            "Thüringen",
            "Th&#252;ringen",
        ]
        state_courts = [
            "OVG",
            "VGH",
            "LSG",
        ]
        cities = [
            "Baden-Baden",
            "Berlin-Brbg.Wedding",
            "Schleswig",
            "Koblenz",
            "Hamm",
        ]
        city_courts = [
            "Amtsgericht",
            "AG",
            "Landgericht",
            "LG",
            "Oberlandesgericht",
            "OLG",
            "OVG",
        ]

        options = []

        for court in federal_courts:
            options.append(court)

        for court in state_courts:
            for state in states:
                options.append(court + " " + state)
                options.append(state + " " + court)

        for c in city_courts:
            for s in cities:
                options.append(c + " " + s)
                options.append(s + " " + c)
        # logger.debug('Court regex: %s' % pattern)

        return r"(?P<court>" + ("|".join(options)) + r")(\s|\.|;|,|:|\))"

    def infer_court(self, file_number: str, match: re.Match, content: str) -> str | None:
        """In some cases it is possible to infer the court from the file number.
        This is currently only implemented for Sozialgerichtsbarkeit ("SG").
        """
        SG_MAPPING = {
            "B": "Bundessozialgericht",
            "L": "LSG",
            "S": "SG",
        }

        if sg_match := re.match(self.get_sozialgerichtsbarkeit_regex(), file_number):
            instance = SG_MAPPING[sg_match.group("instance")]
            court_candidate = self.search_court(match, content)
            if court_candidate and instance in court_candidate:  # we can be sure that the correct court was found
                return court_candidate
            return instance

        return None

    def search_court(self, match: re.Match, content: str) -> str | None:
        """Heuristic search. Not yet very reliably (see error cases in test_case_extractor.py)"""

        court = None

        # Search in surroundings for court names
        for diff in [100, 200, 500]:
            # TODO maybe search left first, then to the right

            start = max(0, match.start(0) - diff)
            end = min(len(content), match.end(0) + diff)
            surrounding = content[start:end]

            # print('Surroundings: %s'  % content[start:end])

            # File number position in surroundings
            fn_pos = match.start(0) - start
            candidates = collections.OrderedDict()

            for court_match in re.finditer(self.get_court_name_regex(), surrounding):
                candidate_pos = round((court_match.start(0) + court_match.end(0)) / 2)  # Position = center
                candidate_dist = abs(fn_pos - candidate_pos)  # Distance to file number

                # print('-- Candidate: %s / pos: %i / dist: %i' % (court_match.group(0), candidate_pos, candidate_dist))

                if candidate_dist not in candidates:
                    candidates[candidate_dist] = court_match
                else:
                    logger.warning(f"Court candidate with same distance exist already: {court_match}")

            # Court is the candidate with smallest distance to file number
            if len(candidates) > 0:
                court = next(iter(candidates.values())).group("court")
                # Stop searching if court was found with this range
                break

        return court

    def get_sozialgerichtsbarkeit_regex(self):
        """
        Sozialgerichtsbarkeit cases have a special, more expanded format, e.g.: B 6 KA 45/13 R
        - instance: Gericht bzw. die Instanz
        - chamber: Kammber bzw. Senat
        - subject_area: Sachgebietskennzeichen
        - number: Laufende Nummer
        - year: Eingangsjahr
        - register: Verfahrensregister (optional)
        """
        pattern = (
            r"(?P<instance>(B|L|S))"
            + r"\s"
            + r"(?P<chamber>[0-9]{1,2})"
            + r"\s"
            + r"(?P<subject_area>(A|AL|AS|AY|BK|BL|EG|KA|KG|KR|KS|LW|P|R|RE|RS|SB|SO|SF|U|ÜG|V|VG|VH|VJ|VK|VS))"
            + r"\s"
            + r"(?P<number>[0-9]{1,6})"
            + r"/"
            + r"(?P<year>[0-9]{2})"
            + r"(?P<register>\s(AR|B|BH|C|GS|K|KH|R|RH|S))?"
        )
        return pattern

    def get_file_number_regex(self):
        """
        Examples:

        1 O 137/15
        Au 5 K 17.31263

        The general way file numbers are structured is:

        <chamber> <code> <number> / <year>

        - chamber: zuständige Richter bzw. Spruchkörper (arabic or roman numbers)
        - code: Registerzeichen
        - number: laufende Nummer (numeric only)
        - separater: / or ,
        - year: Eingangsjahr (numeric, length = 2)


        Sozialgerichtsbarkeit ("SG") cases have a special, more expanded format (e.g.: B 6 KA 45/13 R)
        - instance: Gericht bzw. die Instanz
        - chamber: Kammber bzw. Senat
        - subject_area: Sachgebietskennzeichen
        - number: Laufende Nummer
        - year: Eingangsjahr
        - register: Verfahrensregister (optional)

        However, while the SG file numbers are semantically different (e.g. after the chamber, they contain
        a subject area instead of the code), they syntactically are being matched by the regular file number
        regex, except for the instance and (an optional) register part. So in order to include SG file numbers
        fully, the regex is extended with those two elements.

        TODO Special cases

        BSG: B 6 KA 45/13 R, S 8 AL 144/12
        Bavaria has a different order - <year>.<number>
        - <chamber> <code> <year>.<number>
        """

        # |' + ('|'.join(self.get_codes())) + ')' \

        pattern = (
            r"((?P<instance_for_sg>(B|L|S))\s)?"  # only for SG
            + r"(?P<chamber>([0-9]{1,2})[a-z]?|([IVX]+))"
            + r"\s"
            + "(?P<code>[A-Z][A-Za-z]{0,4})"
            + r"(\s\(([A-Za-z]{1,6})\))?"
            + r"(\s([A-Za-z]{1,6}))?"
            + r"\s"
            + "(?P<number>[0-9]{1,6})"
            + r"(\/|\.)"
            + "(?P<year>[0-9]{2})"
            + r"(\s(?P<register>(AR|B|BH|C|GS|K|KH|R|RH|S)))?"  # only for SG
        )

        return pattern

    def extract_case_ref_markers(self, content: str) -> list[RefMarker]:
        r"""
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

        # TODO More intelligent by search only in sentences.

        # Find all file numbers
        for match in re.finditer(self.get_file_number_regex(), content):
            file_number = match.group(0)

            court = self.infer_court(file_number, match, content) or self.search_court(match, content) or ""

            file_number = match.group(0)
            ref_ids = [
                Ref(ref_type=RefType.CASE, court=court, file_number=file_number)  # TODO date field
            ]
            # TODO maintain order for case+law refs
            marker = RefMarker(text=file_number, start=match.start(0), end=match.end(0), line=0)  # TODO line number
            marker.set_uuid()
            marker.set_references(ref_ids)

            refs.append(marker)

            # print(match.start(0))

        return refs

    def get_codes(self) -> set[str]:
        """Codes used in file numbers"""
        data_files = importlib.resources.files("refex") / "data"
        code_path = data_files / "file_number_codes.csv"

        with importlib.resources.as_file(code_path) as path:
            with open(path) as f:
                codes = []
                for line in f.readlines():
                    cols = line.strip().split(",", 2)

                    # Strip parenthesis
                    code = re.sub(r"\s\((.*?)\)", "", cols[0])

                    codes.append(code)

                return set(codes)
