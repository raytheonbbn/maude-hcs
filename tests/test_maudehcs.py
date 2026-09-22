import json
import math
import pytest
import multiprocessing
import logging

from scipy.stats import ks_2samp
from multiprocessing import Process, Pipe
from multiprocessing.connection import Connection
from typing import Any
from collections.abc import Callable
from pathlib import Path
from pytest_regressions.file_regression import FileRegressionFixture

from .utils.build import build
from .utils.context import TestConfig, TestRunner, RunConfig, mk_id
from .runners.maude_runner import maude_runner
from .runners.smc_runner import smc_runner

logger = logging.getLogger(__name__)

SMC_THRESHOLD = 10.0
KS_THRESHOLD = 10.0

def euclid_feat_distance(feat0: dict, feat1: dict) -> float:
    """Provides a metric for the distance between two feature distributions
    feat0 and feat1 should have keys "mean", "std", and "radius"
    """
    return math.sqrt(
        (feat0["mean"] - feat1["mean"]) ** 2.0 +
        (feat0["std"] - feat1["std"]) ** 2.0 +
        (feat0["radius"] - feat1["radius"]) ** 2.0
    )

def proc_target(run: Callable, sender: Connection, test_cfg: TestConfig, build_dir: Path, run_cfg: RunConfig):
    result = run(test_cfg, build_dir, run_cfg)
    sender.send(result)

def run(test_cfg: TestConfig, build_dir: Path, run_cfg: RunConfig) -> Any:
    """Run this TestConfig with its designated runner, returning the results for comparison.
    The result could be any type serializable into JSON"""

    multiprocessing.set_start_method("spawn", force=True)
    receiver, sender = Pipe(duplex=False)

    run_proc = Process(
        target=proc_target,
        args=(test_cfg.runner.to_func(), sender, test_cfg, build_dir, run_cfg)
    )

    run_proc.start()
    run_proc.join()
    return receiver.recv()

def get_checker(cfg: TestConfig) -> Callable[[Path, Path], None]:
    match cfg.runner:
        case TestRunner.MAUDE: return json_check_fn
        case TestRunner.SMC: return smc_check_fn
        case _: raise Exception("invalid TestRunner")

def naive_smc_check_fn(obtained_filename: Path, expected_filename: Path):
    """Compare the results of an SMC run to a known "good" reference run.
    Both files should contain json of the form {queries: [{"mean": X, "std": Y, "radius": Z}, ...], ...}
    where X Y and Z are floats.
    
    The comparison is made by averaging the "distance" between each pair of queries, interpreting X Y and Z as 3d coordinates.
    This is a kinda silly method, but I'm not yet sure of a better metric on distributions without ECDFs."""

    obtained_str = obtained_filename.read_text()
    obtained_json = json.loads(obtained_str)
    obtained_queries = obtained_json["queries"]

    expected_str = expected_filename.read_text()
    expected_json = json.loads(expected_str)
    expected_queries = expected_json["queries"]

    if not isinstance(obtained_queries, list):
        raise Exception("obtained queries should be a list of objects")
    
    if not isinstance(expected_queries, list):
        raise Exception("obtained queries should be a list of objects")

    n_queries = len(obtained_queries)
    assert n_queries == len(expected_queries)

    total_distance = sum([euclid_feat_distance(feat0, feat1) for feat0, feat1 in zip(obtained_queries, expected_queries)])
    avg_distance = total_distance / n_queries

    assert avg_distance <= SMC_THRESHOLD

def smc_check_fn(obtained_filename: Path, expected_filename: Path):
    obtained_str = obtained_filename.read_text()
    obtained_json = json.loads(obtained_str)
    obtained_results: dict = obtained_json["results"]

    expected_str = expected_filename.read_text()
    expected_json = json.loads(expected_str)
    expected_results: dict = expected_json["results"]

    n_feats = len(obtained_results)
    assert n_feats == len(expected_results)
    assert obtained_results.keys() == expected_results.keys()

    for key in obtained_results.keys():
        assert ks_2samp(
            obtained_results[key]["samples"],
            expected_results[key]["samples"]
        ).statistic <= KS_THRESHOLD # type: ignore

def json_check_fn(obtained_filename: Path, expected_filename: Path):
    """Just compare two json files for equality when interpreted as Python objects"""
    obtained_str = obtained_filename.read_text()
    obtained_json = json.loads(obtained_str)

    expected_str = expected_filename.read_text()
    expected_json = json.loads(expected_str)

    assert obtained_json == expected_json

# parametrization for the tests is handled in conftest.py to allow for selecting different tests based on command-line args

def test_regressions(test_cfg: TestConfig, pytestconfig, file_regression: FileRegressionFixture):
    """Run this test_cfg and compare results to a saved reference result, or save the results if this is the first time"""
    build_dir = build(test_cfg.build_cfg, pytestconfig.run_cfg, test_cfg.ctx.directory)

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

    if pytestconfig.run_cfg.build_only:
        pytest.skip("user requested builds only, skipping test")
    else:
        out = run(test_cfg, build_dir, pytestconfig.run_cfg)

    assert out == test_cfg.expected