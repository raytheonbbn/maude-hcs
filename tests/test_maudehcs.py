import json
import logging
import pytest
import maude
import tempfile

from pathlib import Path
from pytest_regressions.file_regression import FileRegressionFixture

from .utils.context import TestManager, Context, TestConfig
from .runners.maude_runner import regression_maude_runner #, expected_maude_runner

logger = logging.getLogger(__name__)
manager = TestManager()
temp_dir = Path(tempfile.mkdtemp()).resolve()
maude.init()

def smc_check_fn(obtained_filename: Path, expected_filename: Path):
    # Make sure distribution are close enough
    pass

def json_check_fn(obtained_filename: Path, expected_filename: Path):
    obtained_str = obtained_filename.read_text()
    obtained_json = json.loads(obtained_str)

    expected_str = expected_filename.read_text()
    expected_json = json.loads(expected_str)

    assert obtained_json == expected_json

@pytest.mark.parametrize("cfg", manager.regression_test_cfgs())
def test_regressions(file_regression: FileRegressionFixture, cfg: TestConfig):
    out = regression_maude_runner(cfg, Path(temp_dir))
    file_regression.check(out, extension=".json", check_fn=json_check_fn)

# @pytest.mark.parametrize(["ctx", "cfg"], manager.expected_test_pairs)
# def test_expected(ctx: Context, cfg: TestConfig):
#     out = expected_maude_runner(ctx, **cfg.args)
#     assert out == cfg.expected