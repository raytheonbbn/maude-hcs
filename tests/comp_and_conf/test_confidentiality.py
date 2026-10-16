"""Each observable gets a test result; a module fixture shares its model runs."""
from dataclasses import replace

import pytest

from maude_hcs.lib import GLOBALS

from ..utils.confidentiality import load_confidentiality_suite, run_suite, Case, CaseStatus
from ..utils.context import TestConfig, Context, TestRunner
from ..utils.keys import run_cfg_key

CTX_PATH = GLOBALS.TOP_LEVEL_DIR / "tests" / "contexts" / "confidentiality"
SUITE = load_confidentiality_suite(CTX_PATH)

suite_key = pytest.StashKey[list[Case]]()
    
def pytest_generate_tests(metafunc):
    cases = metafunc.config.stash[suite_key]
    if 'case' in metafunc.fixturenames:
        metafunc.parametrize("case", cases)

def test_smoke(case: Case) -> None:
    assert case.traceback is None, f"smoke test failed, traceback:\n{case.traceback}"

def test_statistical(case: Case) -> None:
    if case.status == CaseStatus.INVALID:
        pytest.skip("No relevant packets observed in at least one arm, can't draw conclusions")
    elif case.status == CaseStatus.PENDING:
        raise RuntimeError("Case was never completed, this is a bug")
    else:
        assert case.passed