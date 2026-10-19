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

logger = logging.getLogger(__name__)
manager = TestManager()
run_cfg_key = pytest.StashKey[RunConfig]()

def pytest_addoption(parser) -> None:

    parser.addoption("--composition", action="store_true", help="run the TGEN/HCS composition test suite")
    # parser.addoption("--tgen-samples", type=int, default=None, help="fixed per-case TGEN comparison sample budget")
    # parser.addoption("--tgen-type", help="select a TGEN kind (e.g. ftp or ftpTgen)")
    # parser.addoption("--window_size", type=int, default=None, help="replace the TGEN window list with this single duration in seconds")

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

    # pytest by default has many useful flags, especially -k for selecting tests. See also --log-level, --log-cli-level, -s, 
    # pytest-regressions also adds the flags --force-regen and --regen-all

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

        # log_level=None,
        # log_filter=None,

        build_only=config.getoption("--build"),
        persist=persist,
        results_dir=config.getoption("--results-dir"),

        override_run_time=config.getoption("--override-run-time"),
        timeout=config.getoption("--timeout"),
        partial_smc_comp=config.getoption("--partial-smc-comp"),
    )

    if config.getoption("--copy"):
        pyperclip.copy(str(run_cfg.temp_dir))

    config.stash[run_cfg_key] = run_cfg

    maude.init()

def pytest_collection_modifyitems(session, config, items) -> None:
    run_cfg = config.stash[run_cfg_key]
    reg_only = run_cfg.characterization
    exp_only = run_cfg.known_answer

    def item_filter(item) -> bool:
        if reg_only: return item.name.startswith("test_characterization")
        if exp_only: return item.name.startswith("test_known_answer")
        return True
    
    items[:] = list(filter(item_filter, items))

def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    config = metafunc.config
    run_cfg = config.stash[run_cfg_key]

    def filter_runner(test_cfgs) -> list[Any]:
        return list(filter(
            lambda test_cfg: (run_cfg.runner is None) or test_cfg.runner == run_cfg.runner,
            test_cfgs
        ))

    match metafunc.definition.name:
        case "test_characterization":
            metafunc.parametrize("test_cfg", filter_runner(manager.characterization_test_cfgs()), ids=lambda x: x.mk_id())

        case "test_known_answer":
            metafunc.parametrize("test_cfg", filter_runner(manager.known_answer_test_cfgs()), ids=lambda x: x.mk_id())

        case _:
            raise RuntimeError(f"Unexpected test function name:{metafunc.definition.name}, expected test_characterization or test_known_answer")

# def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter, exitstatus, config: pytest.Config):
#     terminalreporter.write_line("\nbsadlfjhasdifluashdnflkhashdfialushdfalisdufh\n")

def pytest_sessionfinish(session: pytest.Session, exitstatus) -> None:
    run_cfg = session.config.stash[run_cfg_key]
    if not run_cfg.persist: shutil.rmtree(run_cfg.temp_dir)