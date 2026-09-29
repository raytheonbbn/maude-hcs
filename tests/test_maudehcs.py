import json
import pytest
import logging

from typing import Any
from collections.abc import Callable
from pathlib import Path
from pytest_regressions.file_regression import FileRegressionFixture

from .utils.build import build
from .utils.context import TestConfig, TestRunner, RunConfig, mk_id

logger = logging.getLogger(__name__)


# Keep process management separate from model execution so it can be tested
# without starting Maude or building an entire scenario.
from .utils.execution import execute
from .utils.comparison import compare_smc, check_reference


def run(test_cfg: TestConfig, build_dir: Path, run_cfg: RunConfig) -> Any:
    return execute(
        test_cfg.runner.to_func(),
        (test_cfg, build_dir, run_cfg, logging.getLogger("TestSubProcess")),
        timeout=run_cfg.timeout,
        log_dir=build_dir / "logs",
    )

def get_checker(cfg: TestConfig) -> Callable[[Path, Path], None]:
    match cfg.runner:
        case TestRunner.MAUDE: return json_check_fn
        case TestRunner.SMC: return lambda obtained, expected: smc_check_fn(obtained, expected, cfg.comparison)
        case _: raise Exception("invalid TestRunner")

def smc_check_fn(obtained_filename: Path, expected_filename: Path, policy):
    compare_smc(json.loads(obtained_filename.read_text()),
                json.loads(expected_filename.read_text()), policy)

def json_check_fn(obtained_filename: Path, expected_filename: Path):
    """Just compare two json files for equality when interpreted as Python objects"""
    obtained_str = obtained_filename.read_text()
    obtained_json = json.loads(obtained_str)

    expected_str = expected_filename.read_text()
    expected_json = json.loads(expected_str)

    assert obtained_json == expected_json

# parametrization for the tests is handled in conftest.py to allow for selecting different tests based on command-line args

def test_regressions(test_cfg: TestConfig, pytestconfig, file_regression: FileRegressionFixture):
    """Compare against an approved reference; regeneration must be explicit."""
    if not pytestconfig.run_cfg.build_only:
        reference = file_regression.original_datadir / (mk_id(test_cfg) + ".json")
        check_reference(reference, smc=test_cfg.runner == TestRunner.SMC,
                        regenerate=pytestconfig.getoption("force_regen", default=False)
                        or pytestconfig.getoption("regen_all", default=False))
    build_dir = build(test_cfg.build_cfg, pytestconfig.run_cfg, test_cfg.ctx.directory)
    logger.info("Test %s build and logs: %s", mk_id(test_cfg), build_dir)

    if pytestconfig.run_cfg.build_only:
        pytest.skip("user requested builds only, skipping test")
    else:
        out = run(test_cfg, build_dir, pytestconfig.run_cfg)

    file_regression.check(
        json.dumps(out, indent=4),
        extension=".json",
        check_fn=get_checker(test_cfg),
        basename=mk_id(test_cfg)
    )

def test_expected(test_cfg: TestConfig, pytestconfig):
    build_dir = build(test_cfg.build_cfg, pytestconfig.run_cfg, test_cfg.ctx.directory)
    logger.info("Test %s build and logs: %s", mk_id(test_cfg), build_dir)

    if pytestconfig.run_cfg.build_only:
        pytest.skip("user requested builds only, skipping test")
    else:
        out = run(test_cfg, build_dir, pytestconfig.run_cfg)

    assert out == test_cfg.expected, f"{mk_id(test_cfg)}: expected {test_cfg.expected!r}, got {out!r}; logs: {build_dir / 'logs'}"