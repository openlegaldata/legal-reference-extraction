import logging
import os
from unittest import TestCase

from refex.extractor import RefExtractor
from refex.models import RefMarker

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class BaseRefExTest(TestCase):
    resource_dir = os.path.join(os.path.dirname(__file__), 'resources')

    extractor = RefExtractor()

    def assert_refs(self, fixtures):
        for i, test in enumerate(fixtures):
            if 'resource' in test and 'content' not in test:
                with open(os.path.join(self.resource_dir, test['resource'])) as f:
                    test['content'] = ''.join(f.readlines())

            new_content, markers = self.extractor.extract(test['content'])

            ref_ids = []
            for ref in markers:  # type: RefMarker
                ref_ids.extend(ref.get_references())

            # print('-----')
            test['refs'] = sorted(test['refs'])
            ref_ids = sorted(ref_ids)

            logger.debug('actual (%i):   %s' % (len(ref_ids), ref_ids))
            logger.debug('expected (%i): %s' % (len(test['refs']), test['refs']))

            self.assertListEqual(ref_ids, test['refs'], 'Invalid ids returned (test #%i)' % i)