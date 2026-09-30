import json
import math
import pytest
import multiprocessing
import logging
import logging.handlers
import os
import io
import uuid
import time
import traceback

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
KS_THRESHOLD = 2.0
TIMEOUT = 60 * 60 * 6 # 6 hours

def make_check_fn(f: Callable[[str, str], None]) -> Callable[[Path, Path], None]:
    """Given a comparison function `f` between two strings, returns a comparison function between filenames
    that just invokes `f` on the contents of those files."""
    return lambda n0, n1: f(n0.read_text(), n1.read_text())

class ChildProcessErrorWrapper(Exception):
    """Custom exception used to format and output the traceback of a child process."""
    def __init__(self, exception: Exception, tb_string: str):
        self.exception = exception
        self.tb_string = tb_string
    
    def __str__(self):
        return f"\n\n--- Child Process Traceback ---\n{self.tb_string}{type(self.exception).__name__}: {self.exception}"

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

    try:
        log_stdout_filename = mk_id(test_cfg) + ":stdout"
        log_stderr_filename = mk_id(test_cfg) + ":stderr"
        log_stdout_path = build_dir / "logs" / log_stdout_filename
        log_stderr_path = build_dir / "logs" / log_stderr_filename
        log_stdout_path.touch()
        log_stderr_path.touch()

        out_fd = os.open(log_stdout_path, os.O_WRONLY)
        err_fd = os.open(log_stderr_path, os.O_WRONLY)
        os.set_blocking(out_fd, False)
        os.set_blocking(err_fd, False)
        os.dup2(out_fd, 1)
        os.dup2(err_fd, 2)

        # Custom logger to write to file in build directory, so they don't stream raw (uninterceptible) text
        # to our stdout (which is now a StringIO)
        child_logger = logging.getLogger("TestSubProcess")
        child_logger.setLevel(logging.INFO)
        log_filename = mk_id(test_cfg) + ":log"
        child_logger.addHandler(logging.FileHandler(build_dir / "logs" / log_filename))

        result = run(test_cfg, build_dir, run_cfg, child_logger)
        time.sleep(0.1) # Give maude a tiny bit of time to finish all writes to "stdout"

        sender.send(result)
        sender.close()

    except Exception as e:

        # Send back an exception wrapper that still includes the traceback string
        sender.send(ChildProcessErrorWrapper(e, traceback.format_exc()))
        sender.close()

def run(test_cfg: TestConfig, build_dir: Path, run_cfg: RunConfig) -> Any:
    """Run this TestConfig with its designated runner, returning the results for comparison.
    The result could be any type serializable into JSON"""

    multiprocessing.set_start_method("spawn", force=True)
    receiver, sender = Pipe(duplex=False)

    with receiver, sender:

        run_proc = Process(
            target=proc_target,
            args=(test_cfg.runner.to_func(), sender, test_cfg, build_dir, run_cfg)
        )

        run_proc.start()

        # If test doesn't complete within 6 hours, shut it down and raise Exception
        if not receiver.poll(TIMEOUT):
            run_proc.terminate() # interrupt doesn't seem to work, have to use at least terminate
            raise Exception(f"child process didn't complete within {TIMEOUT} seconds ({TIMEOUT / (60 * 60)} hours)")
        
        result = receiver.recv() # CANNOT be delayed until after the join, or send will block
        
        run_proc.join()

        if run_proc.exitcode != 0:
            raise Exception(f"child process finished with nonzero exit code! sent: {result}")

        if isinstance(result, Exception):
            raise result
        
        return result

def get_comp(cfg: TestConfig) -> Callable[[str, str], None]:
    """Get appropriate comparison function for this config"""

    match cfg.runner:
        case TestRunner.MAUDE: return json_comp
        case TestRunner.SMC: return smc_comp
        case _: raise Exception("invalid TestRunner")

def naive_smc_comp(obtained: str, expected: str):
    """Compare the results of an SMC run to a known "good" reference run.
    Both strings should contain json of the form {queries: [{"mean": X, "std": Y, "radius": Z}, ...], ...}
    where X Y and Z are floats.
    
    The comparison is made by averaging the "distance" between each pair of queries, interpreting X Y and Z as 3d coordinates.
    This is a kinda silly method, but I'm not yet sure of a better metric on distributions without ECDFs."""

    obtained_json = json.loads(obtained)
    obtained_queries = obtained_json["queries"]

    expected_json = json.loads(expected)
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

def smc_comp(obtained: str, expected: str):
    obtained_json: dict = json.loads(obtained)
    obtained_results: dict = obtained_json["results"]

    expected_json: dict = json.loads(expected)
    expected_results: dict = expected_json["results"]

    shared_top_keys = set(obtained_json.keys()).intersection(expected_json.keys()).difference(set(["results"]))

    for key in shared_top_keys:
        obt_val = obtained_json[key]
        exp_val = expected_json[key]

        if obt_val != exp_val:
            logger.warning("Obtained run parameters don't match expected parameters! Comparing the two runs might not be meaningful.")
            logger.warning("Obtained %s: %s", key, obt_val)
            logger.warning("Expected %s: %s", key, exp_val)

    assert len(obtained_results) == len(expected_results)
    assert obtained_results.keys() == expected_results.keys()

    for key in obtained_results.keys():
        assert ks_2samp(
            obtained_results[key]["samples"],
            expected_results[key]["samples"]
        ).statistic <= KS_THRESHOLD # type: ignore

def json_comp(obtained: str, expected: str):
    """Just compare two json files for equality when interpreted as Python objects"""
    obtained_json = json.loads(obtained)
    expected_json = json.loads(expected)
    assert obtained_json == expected_json

# parametrization for the tests is handled in conftest.py to allow for selecting different tests based on command-line args

def test_regression(test_cfg: TestConfig, pytestconfig, file_regression: FileRegressionFixture):
    """Run this test_cfg and compare results to a saved reference result, or save the results if this is the first time"""
    build_dir = build(test_cfg.build_cfg, pytestconfig.run_cfg, test_cfg.ctx.directory)

    if pytestconfig.run_cfg.build_only:
        pytest.skip("user requested builds only, skipping test")
    else:
        out = run(test_cfg, build_dir, pytestconfig.run_cfg)

    if pytestconfig.run_cfg.results_dir is not None:
        if not os.path.isdir(pytestconfig.run_cfg.results_dir):
            os.mkdir(pytestconfig.run_cfg.results_dir)
        with open(Path(pytestconfig.run_cfg.results_dir) / f"{mk_id(test_cfg)}.json", 'w') as f:
            json.dump(out, f, indent=4)


    file_regression.check(
        json.dumps(out, indent=4),
        extension=".json",
        check_fn=make_check_fn(get_comp(test_cfg)),
        basename=mk_id(test_cfg)
    )

def test_expected(test_cfg: TestConfig, pytestconfig):
    build_dir = build(test_cfg.build_cfg, pytestconfig.run_cfg, test_cfg.ctx.directory)

    if pytestconfig.run_cfg.build_only:
        pytest.skip("user requested builds only, skipping test")
    else:
        out = run(test_cfg, build_dir, pytestconfig.run_cfg)

    if pytestconfig.run_cfg.results_dir is not None:
        if not os.path.isdir(pytestconfig.run_cfg.results_dir):
            os.mkdir(pytestconfig.run_cfg.results_dir)
        with open(Path(pytestconfig.run_cfg.results_dir) / f"{mk_id(test_cfg)}.json", 'w') as f:
            json.dump(out, f, indent=4)

    if isinstance(out, dict):
        out = json.dumps(out, indent=4)

    if test_cfg.expected is not None:
        get_comp(test_cfg)(out, test_cfg.expected)
    elif test_cfg.expected_file is not None:
        exp_file = test_cfg.ctx.directory / "expected" / f"{test_cfg.expected_file}.json"
        get_comp(test_cfg)(out, exp_file.read_text())
    else:
        raise RuntimeError("test_cfg passed to test_expected must set either expected or expected_file attributes")