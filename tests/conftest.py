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

from .utils.context import TestManager, Context, TestConfig, TestRunner, RunConfig, BuildConfig, TestSuiteType
from .utils.keys import run_cfg_key

logger = logging.getLogger(__name__)
manager = TestManager()

SUITES = ["REGRESSION", "COMPOSITION", "CONFIDENTIALITY", "ALL"]

def pytest_addoption(parser) -> None:

    test_suite_ty = lambda x: TestSuiteType.from_name(x)
    parser.addoption(
        "--suite",
        help=f"comma-separated list of test suites to run. Options: {", ".join(SUITES)}",
        type=test_suite_ty,
        default=TestSuiteType.REGRESSION
    )

    # General options apply to all (or most) test suites
    parser.addoption("--temp-dir", help="manually choose a directory to store built environments. Implies `--persist`")
    parser.addoption("--build", action="store_true", help="only run build commands, don't actually execute tests")
    parser.addoption("--persist", action="store_true", help="persist the temporary build directory after tests complete")
    parser.addoption("--results-dir", help="save test results under specified directory (different from snapshot!)")
    parser.addoption("--override-run-time", help="override run time for all selected tests", type=int)
    parser.addoption("--timeout", help="set max time in seconds a test can take before automatically failing", type=int)

    parser.addoption("--copy", action="store_true", help="copy the path to the temp directory to system clipboard")

    # Options for regression test suite
    test_runner_ty = lambda x: TestRunner(str.lower(x))
    parser.addoption("--runner", help="only run tests using the specified runner", type=test_runner_ty)
    parser.addoption("--characterization", action="store_true", help="only run characterization tests")
    parser.addoption("--known-answer", action="store_true", help="only run known-answer tests")
    parser.addoption(
        "--partial-smc-comp",
        action="store_true",
        help="allow partial comparisons of smc results when they don't measure exactly the same features. In that case, only" \
        "the features measured by both runs will be compared. This can be used e.g. to validate a short run against a long reference run.")
    
    # Options for confidentiality test suite
    parser.addoption("--smoke", help="just make sure the confidentiality tests build and run, don't evaluate distinguishability")

@pytest.fixture
def run_cfg(request: pytest.FixtureRequest):
    return request.config.stash[run_cfg_key]

def pytest_configure(config) -> None:
    td_opt = config.getoption("--temp-dir")
    persist = config.getoption("--persist")
    suite = config.getoption("--suite")

    if td_opt is not None:
        temp_dir = Path(td_opt).resolve()
        os.mkdir(temp_dir)
        persist=True
    else:
        temp_dir = Path(tempfile.mkdtemp()).resolve()
    
    if suite != TestSuiteType.REGRESSION:
        assert config.getoption("--runner") is None
        assert config.getoption("--characterization") is None
        assert config.getoption("--known-answer") is None

    run_cfg = RunConfig(
        suite=suite,

        temp_dir=temp_dir,
        build_only=config.getoption("--build"),
        persist=persist,
        results_dir=config.getoption("--results-dir"),
        override_run_time=config.getoption("--override-run-time"),
        timeout=config.getoption("--timeout"),

        runner=config.getoption("--runner"),
        characterization=config.getoption("--characterization"),
        known_answer=config.getoption("--known-answer"),
        partial_smc_comp=config.getoption("--partial-smc-comp"),

        smoke=config.getoption("--smoke"),
    )

    if config.getoption("--copy"):
        pyperclip.copy(str(run_cfg.temp_dir))

    config.stash[run_cfg_key] = run_cfg

    maude.init()

# We do all modification at the top level because every _modifyitems function sees ALL tests for the run anyways
def pytest_collection_modifyitems(session, config, items: list[pytest.Item]) -> None:
    run_cfg: RunConfig = config.stash[run_cfg_key]
    selected = []
    deselected = []

    for item in items:
        reg_type_mark = item.get_closest_marker("regression_test_type")
        runner_mark = item.get_closest_marker("runner")

        if reg_type_mark is not None:
            reg_type = reg_type_mark.args[0]
            if (reg_type == "characterization" and run_cfg.known_answer) or (reg_type == "known_answer" and run_cfg.characterization):
                deselected.append(item)
                continue

        if runner_mark is not None and run_cfg.runner is not None:
            item_runner = runner_mark.args[0]
            if item_runner != run_cfg.runner:
                deselected.append(item)
                continue

        if "confidentiality" in str(item.name) and not (TestSuiteType.CONFIDENTIALITY & run_cfg.suite):
            deselected.append(item)
            continue

        selected.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)

    items[:] = selected

def pytest_sessionfinish(session: pytest.Session, exitstatus) -> None:
    run_cfg = session.config.stash[run_cfg_key]
    if not run_cfg.persist: shutil.rmtree(run_cfg.temp_dir)