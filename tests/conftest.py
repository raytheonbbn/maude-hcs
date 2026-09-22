import shutil
import logging
import pytest
import maude
import tempfile
import pyperclip
import os
import multiprocessing

from pathlib import Path
from pytest_regressions.file_regression import FileRegressionFixture
from maude_hcs.lib import GLOBALS

from .utils.context import TestManager, Context, TestConfig, TestRunner, RunConfig, BuildConfig, mk_id

logger = logging.getLogger(__name__)
manager = TestManager()

def pytest_addoption(parser):
    parser.addoption("--pp", action="store_true", help="attempt to pretty-print the return value for each selected test")
    parser.addoption("--build", action="store_true", help="only run build commands, don't test")
    parser.addoption("--persist", action="store_true", help="persist the temporary build directory after tests complete")

    parser.addoption("--runner", help="only run tests using the specified runner", type=TestRunner)
    parser.addoption("--regression", action="store_true", help="only run regression tests")
    parser.addoption("--expected", action="store_true", help="only run expected-value tests")

    parser.addoption("--copy", action="store_true", help="copy the path to the temp directory to system clipboard")
    parser.addoption("--tempdir", help="manually choose a directory to store built environments. Implies `--persist`.")

    # pytest by default has many useful flags, especially -k for selecting tests. See also --log-level, --log-cli-level, -s, 
    # pytest-regressions also adds the flags --force-regen and --regen-all

def pytest_configure(config):
    td_opt = config.getoption("--tempdir")
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

        regression=config.getoption("--regression"),
        expected=config.getoption("--expected"),

        log_level=None,
        log_filter=None,
        pp=config.getoption("--pp"), # type: ignore

        build_only=config.getoption("--build"), # type: ignore
        persist=persist
    )

    if config.getoption("--copy"):
        pyperclip.copy(str(run_cfg.temp_dir))

    assert "run_cfg" not in dir(config)
    config.run_cfg = run_cfg

    maude.init()

def pytest_collection_modifyitems(session, config, items):
    reg_only = config.run_cfg.regression
    exp_only = config.run_cfg.expected

    def item_filter(item):
        if reg_only: return item.name == "test_regression"
        if exp_only: return item.name == "test_expected"
        return True

    items[:] = list(filter(item_filter, items))

def pytest_generate_tests(metafunc: pytest.Metafunc):
    config = metafunc.config
    run_cfg = config.run_cfg # type: ignore

    def filter_runner(test_cfgs):
        return list(filter(
            lambda test_cfg: (run_cfg.runner is None) or test_cfg.runner == run_cfg.runner,
            test_cfgs
        ))
    
    if metafunc.definition.name == "test_regressions":
        metafunc.parametrize("test_cfg", filter_runner(manager.regression_test_cfgs()), ids=mk_id)

    if metafunc.definition.name == "test_expected":
        metafunc.parametrize("test_cfg", filter_runner(manager.expected_test_cfgs()), ids=mk_id)

# def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter, exitstatus, config: pytest.Config):
#     terminalreporter.write_line("\nbsadlfjhasdifluashdnflkhashdfialushdfalisdufh\n")

def pytest_sessionfinish(session: pytest.Session, exitstatus):
    if not session.config.run_cfg.persist: shutil.rmtree(session.config.run_cfg.temp_dir) #type: ignore