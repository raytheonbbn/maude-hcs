import shutil
import logging
import pytest
import maude
import tempfile
import pyperclip
import os
import multiprocessing
import random

from typing import Any
from pathlib import Path
from pytest_regressions.file_regression import FileRegressionFixture
from maude_hcs.lib import GLOBALS

from ..utils.context import TestManager, Context, TestConfig, TestRunner, RunConfig, BuildConfig
from ..utils.confidentiality import Case, load_confidentiality_suite, run_suite as run_conf_suite
from ..utils.context import TestConfig, Context, TestRunner
from ..utils.keys import run_cfg_key

from .test_single_tgens import suite_key

logger = logging.getLogger(__name__)
manager = TestManager()

def pytest_addoption(parser) -> None:

    parser.addoption("--build", action="store_true", help="only run build commands, don't test")
    parser.addoption("--persist", action="store_true", help="persist the temporary build directory after tests complete")

    test_runner_ty = lambda x: TestRunner(str.lower(x))
    parser.addoption("--runner", help="only run tests using the specified runner", type=test_runner_ty)
    parser.addoption("--characterization", action="store_true", help="only run characterization tests")
    parser.addoption("--known-answer", action="store_true", help="only run known-answer tests")

    parser.addoption("--copy", action="store_true", help="copy the path to the temp directory to system clipboard")
    parser.addoption("--temp-dir", help="manually choose a directory to store built environments. Implies `--persist`")
    parser.addoption("--results-dir", help="save test results under specified directory (different from snapshot!)")

    parser.addoption("--override-run-time", help="override run time for all selected tests", type=int)
    parser.addoption("--timeout", help="set max time in seconds a test can take before automatically failing", type=int)

    parser.addoption(
        "--partial-smc-comp",
        action="store_true",
        help="allow partial comparisons of smc results when they don't measure exactly the same features. In that case, only" \
        "the features measured by both runs will be compared. This can be used e.g. to validate a short run against a long reference run.")

@pytest.fixture
def run_cfg(request: pytest.FixtureRequest):
    return request.config.stash[run_cfg_key]

def pytest_configure(config) -> None:
    td_opt = config.getoption("--temp-dir")
    persist = config.getoption("--persist")

    if td_opt is not None:
        temp_dir = Path(td_opt).resolve()
        os.mkdir(temp_dir)
        persist=True
    else:
        temp_dir = Path(tempfile.mkdtemp()).resolve()

    run_cfg = RunConfig(
        temp_dir=temp_dir,

        runner=config.getoption("--runner"),

        composition=config.getoption("--composition"),
        characterization=config.getoption("--characterization"),
        known_answer=config.getoption("--known-answer"),

        build_only=config.getoption("--build"),
        persist=persist,
        results_dir=config.getoption("--results-dir"),

        override_run_time=config.getoption("--override-run-time"),
        timeout=config.getoption("--timeout"),
        partial_smc_comp=config.getoption("--partial-smc-comp"),
    )

    if config.getoption("--copy"):
        pyperclip.copy(str(run_cfg.temp_dir))

    suite = load_confidentiality_suite(GLOBALS.TOP_LEVEL_DIR / "tests" / "contexts" / "confidentiality")
    config.stash[run_cfg_key] = run_cfg
    config.stash[suite_key] = run_conf_suite(suite, run_cfg, False)

    maude.init()

def pytest_sessionfinish(session: pytest.Session, exitstatus) -> None:
    run_cfg = session.config.stash[run_cfg_key]
    if not run_cfg.persist: shutil.rmtree(run_cfg.temp_dir)