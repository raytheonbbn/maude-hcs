import shutil
import logging
import pytest
import tempfile
import pyperclip

from pathlib import Path

from .utils.context import TestManager, TestRunner, RunConfig, mk_id

logger = logging.getLogger(__name__)
# Discover contexts only when the integration harness is collected. Framework
# unit tests must remain runnable even when a model definition is broken.
manager = None

def pytest_addoption(parser):
    parser.addoption("--timeout", type=float, default=300.0, help="maximum seconds per model execution")
    parser.addoption("--pp", action="store_true", help="attempt to pretty-print the return value for each selected test")
    parser.addoption("--build", action="store_true", help="only run build commands, don't test")
    parser.addoption("--persist", action="store_true", help="persist the temporary build directory after tests complete")

    test_runner_ty = lambda x: TestRunner(str.lower(x))
    parser.addoption("--runner", help="only run tests using the specified runner", type=test_runner_ty)
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
        # A distinct worker directory avoids xdist workers racing over the same
        # user-supplied directory. Never delete an existing user directory.
        root = Path(td_opt).resolve()
        root.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="pytest-", dir=root))
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
        persist=persist,
        timeout=config.getoption("--timeout"),
    )

    if config.getoption("--copy"):
        pyperclip.copy(str(run_cfg.temp_dir))

    assert "run_cfg" not in dir(config)
    config.run_cfg = run_cfg

    config.addinivalue_line("markers", "smoke: fixed-seed quantitative smoke test")
    config.addinivalue_line("markers", "statistical: distributional regression test")
    config.addinivalue_line("markers", "correctness: explicit model correctness assertion")

def pytest_collection_modifyitems(session, config, items):
    reg_only = config.run_cfg.regression
    exp_only = config.run_cfg.expected

    selected, deselected = [], []
    for item in items:
        name = getattr(item, "originalname", item.name.split("[", 1)[0])
        keep = (not reg_only or name == "test_regressions") and (not exp_only or name == "test_expected")
        (selected if keep else deselected).append(item)
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def pytest_generate_tests(metafunc: pytest.Metafunc):
    global manager
    if metafunc.definition.name not in {"test_regressions", "test_expected"}:
        return
    if manager is None:
        manager = TestManager(Path(__file__).parent / "contexts")
    config = metafunc.config
    run_cfg = config.run_cfg # type: ignore

    def filter_runner(test_cfgs):
        return list(filter(
            lambda test_cfg: (run_cfg.runner is None) or test_cfg.runner == run_cfg.runner,
            test_cfgs
        ))
    
    if metafunc.definition.name == "test_regressions":
        configs = filter_runner(manager.regression_test_cfgs())
        params = []
        for cfg in configs:
            if cfg.runner == TestRunner.SMC:
                from .utils.comparison import validate_policy
                validate_policy(cfg.comparison)
                mark = pytest.mark.smoke if cfg.comparison["mode"] == "smoke" else pytest.mark.statistical
                params.append(pytest.param(cfg, marks=mark))
            else:
                params.append(cfg)
        metafunc.parametrize("test_cfg", params, ids=mk_id)

    if metafunc.definition.name == "test_expected":
        metafunc.parametrize("test_cfg", [pytest.param(cfg, marks=pytest.mark.correctness) for cfg in filter_runner(manager.expected_test_cfgs())], ids=mk_id)

def pytest_sessionfinish(session: pytest.Session, exitstatus):
    cfg = session.config.run_cfg
    # Failure logs are useful precisely when the caller forgot --persist.
    if not cfg.persist and exitstatus == 0:
        shutil.rmtree(cfg.temp_dir)
    elif exitstatus != 0 or cfg.persist:
        reporter = session.config.pluginmanager.getplugin("terminalreporter")
        if reporter:
            reporter.write_line(f"Test builds/logs retained at: {cfg.temp_dir}")
