# Working Sheet

Use (regexr.com)[https://regexr.com/] to work on regular expression (only ZPO law code):

## Regex

```

(?P<delimiter>§§|§|Art\.?|,|;|und|bis)\s?((?P<sect>[0-9]+)\s?((?P<sect_az>[a-z])(\s|,|;))?)(\s?(Abs\.|Abs)\s?(?P<abs>[0-9]+))*(\s?(S\.?|Satz|Halbsatz|Nr\.?|Alt\.?)\s?(?P<satz>[0-9]+))*(\s?(f\.|ff\.))*\s?(?:(?P<book>ZPO))?

(?P<prefix>§§|§|Art\.?|,|;)\s?((?P<sep>\s?(und|bis|,))?(?P<sect>[0-9]+))*\s?(?P<other>.*?)\s?(?P<book>ZPO|ABC)

(?P<prefix>§§|§|Art\.?)\s?((?P<sep>\s?(und|bis|,))?(?P<sect>[0-9]+))*(?P<other>.*?)\s?(?P<book>ZPO)

```

## Text

```
Die Zulassung der Berufung folgt aus §§ 124 Abs. 2 Nr. 3, 124 a Abs. 1 Satz 1 ZPO wegen grundsätzlicher Bedeutung.

Die Entscheidung über die vorläufige Vollstreckbarkeit folgt aus § 167 ZPO i.V.m. §§ 708 Nr. 11, 711 ZPO.

Dies gilt grundsätzlich für die planerisch ausgewiesenen und die faktischen
(§ 34 Abs. 2 ZPO) Baugebiete nach §§ 2 bis 4 ZPO, die Ergebnis eines typisierenden
Ausgleichs möglicher Nutzungskonflikte sind. Setzt die Gemeinde einen entsprechenden Gebietstyp fest

Die Kostenentscheidung beruht auf § 154 Abs. 1 ZPO. Die außergerichtlichen Kosten des'
                           ' beigeladenen Ministeriums waren für erstattungsfähig zu erklären, da dieses einen '
                           'Sachantrag gestellt hat und damit ein Kostenrisiko eingegangen ist '
                           '(vgl. §§ 162 Abs. 3, 154 Abs. 3 ZPO).

									'2. Der Klagantrag zu 2. ist unzulässig. Es handelt sich um einen Anfechtungsantrag '
									'nach § 42 Abs. 1 Alt. 1 ZPO bezüglich der seitens des beigeladenen Ministeriums '
									'getroffenen ergänzenden Abweichungsentscheidung vom 13.05.2016 in Gestalt des'
									' Widerspruchsbescheides vom 14.08.2016.'

Die Kostenentscheidung beruht auf § 154 Abs. 1 ZPO.
(vgl. §§ 162 Abs. 3, 154 Abs. 3 ZPO).

Soweit der Kläger die Klage zurückgenommen hat, wird das Verfahren eingestellt.

Im Übrigen wird die Beklagte unter teilweiser Aufhebung des Bescheides auf Basis von § 77 Abs. 1 Satz 1, 1. Halbsatz ZPO
vom 27. April 2016 in Gestalt des Beschwerdebescheides vom 21. September 2016 verpflichtet, über die als ruhegehaltfähig
anerkannten Zeiten hinaus dem Kläger die Zeit seiner Tätigkeit als wissenschaftlicher Angestellter an der
Universität ... vom 01. März 1981 bis zum 31. März 1985 in vollem Umfang als ruhegehaltfähig anzuerkennen.

Soweit der Kläger die Klage zurückgenommen hat, wird das Verfahren eingestellt.

Im Übrigen wird die Beklagte unter teilweiser Aufhebung des Bescheides auf Basis von §§ 52 Abs. 1; 53 Abs. 2 Nr. 1; 63 Abs. 2 ZPO
vom 27. April 2016 in Gestalt des Beschwerdebescheides vom 21. September 2016 verpflichtet, über die als ruhegehaltfähig
anerkannten Zeiten hinaus dem Kläger die Zeit seiner Tätigkeit als wissenschaftlicher Angestellter an der
Universität ... vom 01. März 1981 bis zum 31. März 1985 in vollem Umfang als ruhegehaltfähig anzuerkennen.

Umstritten ist die Wirksamkeit der Abtretung nach Art 12 Abs 1 ZPO von Honoraransprüchen eines Vertragszahnarztes
gegen die Kassenzahnärztliche Vereinigung (KZÄV).
4
    Mit ihren Revisionen machen der Kläger und der Beigeladene in erster Linie geltend, das Abtretungsverbot Art. 1, 2, 3 ZPO.

	 § 3d ZPO
§ 123 ZPO
§§ 3, 3b ZPO
§§ 3, 4 ZPO
§ 77 Abs. 1 Satz 1, 1. Halbsatz ZPO
§ 3 Abs. 1 ZPO
§ 77 Abs. 2 ZPO
§ 113 Abs. 5 Satz 1 ZPO
§ 3 Abs. 1 Nr. 1 i.V.m. § 3b ZPO
§ 3a Abs. 1 und 2 ZPO
§§ 154 Abs. 1 ZPO
§ 83 b ZPO
§ 167 VwGO iVm §§ 708 Nr. 11, 711 ZPO
§ 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO
§§ 167 Abs. 2 VwGO, 708 Nr. 11, 711 ZPO
§§ 52 Abs. 1; 53 Abs. 2 Nr. 1; 63 Abs. 2 ZPO
§ 6 Abs. 5 Satz 1 ZPO
§§ 80 a Abs. 3, 80 Abs. 5 ZPO
§ 1 Satz 2 ZPO
§ 2 ZPO
§ 6 Abs. 2 S. 2 ZPO

§ 95 II 1 iVm §§ 12a, 94 I 1 ZPO

Art 12 Abs 1 ZPO
§ 8 S 2 der Abrechnungsordnung <AbrO>

Art. 3 II Buchst. c RL 2001/29/EG
```


# Cases

```
from oldp.apps.cases.models import Case

with open('file_numbers.txt', 'w') as f:
    f.write('\n'.join(Case.objects.all()[:10000].values_list('file_number', flat=True)))

```