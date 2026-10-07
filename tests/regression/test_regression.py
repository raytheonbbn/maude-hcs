import json
import pytest
import multiprocessing
import logging
import os
import time
import traceback

from multiprocessing import Process, Pipe
from multiprocessing.connection import Connection
from collections.abc import Callable
from pathlib import Path
from dataclasses import asdict
from pytest_regressions.file_regression import FileRegressionFixture

from maude_hcs.query import parse_quatex
from maude_hcs.lib import GLOBALS

from ..utils.build import build
from ..utils.context import TestConfig, TestRunner, RunConfig
from ..utils.comp import validate_params, validate_feats, make_check_fn, get_comp

logger = logging.getLogger(__name__)

TIMEOUT = 60 * 60 * 6 # 6 hours

class ChildProcessErrorWrapper(Exception):
    """Custom exception used to format and output the traceback of a child process."""
    def __init__(self, exception: Exception, tb_string: str):
        self.exception = exception
        self.tb_string = tb_string
    
    def __str__(self):
        return f"\n\n--- Child Process Traceback ---\n{self.tb_string}{type(self.exception).__name__}: {self.exception}"

def proc_target(run: Callable, sender: Connection, test_cfg: TestConfig, build_dir: Path, run_cfg: RunConfig) -> None:

    try:
        log_stdout_filename = test_cfg.mk_id() + ":stdout"
        log_stderr_filename = test_cfg.mk_id() + ":stderr"
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
        log_filename = test_cfg.mk_id() + ":log"
        child_logger.addHandler(logging.FileHandler(build_dir / "logs" / log_filename))

        result = run(test_cfg, build_dir, run_cfg, child_logger)
        time.sleep(0.1) # Give maude a tiny bit of time to finish all writes to "stdout"

        sender.send(result)
        sender.close()

    except Exception as e:

        # Send back an exception wrapper that still includes the traceback string
        sender.send(ChildProcessErrorWrapper(e, traceback.format_exc()))
        sender.close()

def run(test_cfg: TestConfig, build_dir: Path, run_cfg: RunConfig) -> str:
    """Run this TestConfig with its designated runner, returning the results for comparison.
    The result is always returned as a string, but may be interpreted in various ways
    (e.g. as a JSON dict) depending on the specific TestRunner used."""

    multiprocessing.set_start_method("spawn", force=True)
    receiver, sender = Pipe(duplex=False)

    with receiver, sender:

        run_proc = Process(
            target=proc_target,
            args=(test_cfg.runner.to_func(), sender, test_cfg, build_dir, run_cfg)
        )

        run_proc.start()

        # If timeout is set and test doesn't complete within timeout, shut it down and raise Exception
        if run_cfg.timeout is not None:
            if not receiver.poll(run_cfg.timeout):
                run_proc.terminate() # interrupt doesn't seem to work, have to use at least terminate
                raise Exception(f"child process didn't complete within {run_cfg.timeout} seconds ({run_cfg.timeout / (60 * 60)} hours)")
        
        result = receiver.recv() # CANNOT be delayed until after the join, or send will block
        
        run_proc.join()

        if run_proc.exitcode != 0:
            raise Exception(f"child process finished with nonzero exit code! sent: {result}")

        if isinstance(result, Exception):
            raise result
        
        return result

# parametrization for the tests is handled in conftest.py to allow for selecting different tests based on command-line args

def common_test_handler(test_cfg: TestConfig, build_dir: Path, run_cfg: RunConfig) -> str:
    if run_cfg.build_only:
        pytest.skip("user requested builds only, skipping test")
    elif test_cfg.obtained_file is not None:
        result = json.loads(test_cfg.obtained_file.read_text())
    else:
        result = run(test_cfg, build_dir, run_cfg)

    if run_cfg.results_dir is not None:
        if not os.path.isdir(run_cfg.results_dir):
            os.mkdir(run_cfg.results_dir)
        with open(Path(run_cfg.results_dir) / f"{test_cfg.mk_id()}.json", 'w') as f:
            json.dump(result, f, indent=4)

    return result

def get_inc_params_and_feats(build_dir, test_cfg) -> tuple[dict, set]:
    queries = parse_quatex((build_dir / "test.quatex").read_text())
    inc_params = asdict(test_cfg.build_cfg.gen_args.params)
    inc_feats = set(map(lambda x: x.to_name(), queries))
    return (inc_params, inc_feats)

def get_exp_params_and_feats(expected: str) -> tuple[dict, set]:
    expected_json: dict = json.loads(expected)
    exp_params = {k: v for k, v in expected_json.items() if k != "results"}
    exp_feats = set(expected_json["results"].keys())
    return (exp_params, exp_feats)

def get_obt_params_and_feats(result: str) -> tuple[dict, set]:
    result_dict = json.loads(result)
    obt_params = {k: v for k, v in result_dict.items() if k != "results"}
    obt_feats = set(result_dict["results"].keys())
    return (obt_params, obt_feats)

def test_characterization(test_cfg: TestConfig, run_cfg: RunConfig, file_regression: FileRegressionFixture) -> None:
    """Characterization tests only compare test results to a previously snapshotted "approved" result
    of the same test. If the snapshot is incorrect, results of this test are misleading!"""

    # Path to the saved reference snapshot, or where it should be saved if it doesn't yet exist.
    fullpath = GLOBALS.TOP_LEVEL_DIR / "tests" / "snapshots" / f"{test_cfg.mk_id()}.json"

    # Path to (usually) temporary build directory where the test should be run
    build_dir = build(test_cfg.build_cfg, run_cfg, test_cfg.ctx.directory)

    # If a reference snapshot exists, make sure that its features are the same as the ones we're about to query
    # (or at least warn if they're different and --partial-smc-comp was used)
    if fullpath.is_file() and test_cfg.runner == TestRunner.SMC:
        inc_params, inc_feats = get_inc_params_and_feats(build_dir, test_cfg)
        exp_params, exp_feats = get_exp_params_and_feats(fullpath.read_text())

        validate_feats(inc_feats, exp_feats, run_cfg)
        validate_params(inc_params, exp_params)

        result = common_test_handler(test_cfg, build_dir, run_cfg)

        assert get_obt_params_and_feats(result) == (inc_params, inc_feats)

    else:
        result = common_test_handler(test_cfg, build_dir, run_cfg)

    file_regression.check(
        result,
        check_fn=make_check_fn(get_comp(test_cfg, run_cfg)),
        fullpath=fullpath,
    )
    
def test_known_answer(test_cfg: TestConfig, run_cfg: RunConfig) -> None:
    """We use this test function when we already know the correct
    (or approximately correct) answer to compare test results to"""

    # Path to (usually) temporary build directory where the test should be run
    build_dir = build(test_cfg.build_cfg, run_cfg, test_cfg.ctx.directory)

    if test_cfg.expected is not None:
        expected = test_cfg.expected
    elif test_cfg.expected_file is not None:
        expected = (test_cfg.ctx.directory / "expected" / f"{test_cfg.expected_file}.json").read_text()
    else:
        raise RuntimeError("test_cfg passed to known_answer_test must set either expected or expected_file attributes")

    # If we're running an SMC test, ensure expected features are the same as the "incoming" ones
    #  we're about to query (or at least warn if they're different and --partial-smc-comp was used)
    if test_cfg.runner == TestRunner.SMC:
        inc_params, inc_feats = get_inc_params_and_feats(build_dir, test_cfg)
        exp_params, exp_feats = get_exp_params_and_feats(expected)

        validate_feats(inc_feats, exp_feats, run_cfg)
        validate_params(inc_params, exp_params)

        result = common_test_handler(test_cfg, build_dir, run_cfg)

        assert get_obt_params_and_feats(result) == (inc_params, inc_feats)

    else:
        result = common_test_handler(test_cfg, build_dir, run_cfg)

    get_comp(test_cfg, run_cfg)(result, expected)