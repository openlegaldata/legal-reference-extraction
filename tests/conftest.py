import importlib.resources
import logging
import os
from pathlib import Path

import pytest

from refex.extractor import RefExtractor

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

RESOURCE_DIR = Path(__file__).parent / "resources"


@pytest.fixture()
def extractor():
    e = RefExtractor()
    e.do_law_refs = True
    e.do_case_refs = True
    return e


@pytest.fixture()
def law_extractor():
    e = RefExtractor()
    e.do_law_refs = True
    e.do_case_refs = False
    return e


@pytest.fixture()
def case_extractor():
    e = RefExtractor()
    e.do_law_refs = False
    e.do_case_refs = True
    return e


def get_book_codes_from_file(file_name="law_book_codes.txt"):
    data_files = importlib.resources.files("refex") / "data"
    code_path = data_files / file_name

    with importlib.resources.as_file(code_path) as path:
        with open(path) as f:
            return [line.strip() for line in f.readlines()]


def assert_refs(extractor, fixtures, is_html: bool = False):
    for i, test in enumerate(fixtures):
        if "resource" in test and "content" not in test:
            with open(os.path.join(RESOURCE_DIR, test["resource"])) as f:
                test["content"] = "".join(f.readlines())

        new_content, markers = extractor.extract(test["content"], is_html)

        ref_ids = []
        for ref in markers:  # type: RefMarker
            ref_ids.extend(ref.get_references())

        test["refs"] = sorted(test["refs"])
        ref_ids = sorted(ref_ids)

        logger.debug("actual (%i):   %s", len(ref_ids), ref_ids)
        logger.debug("expected (%i): %s", len(test["refs"]), test["refs"])

        assert ref_ids == test["refs"], f"Invalid ids returned (test #{i})"
