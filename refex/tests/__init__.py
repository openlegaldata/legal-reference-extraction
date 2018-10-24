import logging
from unittest import TestCase

from refex.extractor import RefExtractor
from refex.models import RefMarker

logger = logging.getLogger(__name__)


class BaseRefExTest(TestCase):
    extractor = RefExtractor()

    def assert_refs(self, fixtures):
        for i, test in enumerate(fixtures):
            new_content, markers = self.extractor.extract(test['content'])

            ref_ids = []
            for ref in markers:  # type: RefMarker
                ref_ids.extend(ref.get_references())

            # print('-----')

            logger.debug('actual: %s' % ref_ids)
            logger.debug('fixtures: %s' % test['refs'])

            self.assertListEqual(ref_ids, test['refs'], 'Invalid ids returned (test #%i)' % i)