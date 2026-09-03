import json
import logging
import pytest
import maude

from pathlib import Path
from pytest_regressions.file_regression import FileRegressionFixture

from ..utils.setups import TestManager, Setup, TestConfig
from ..runners.maude_runner import maude_runner

logger = logging.getLogger(__name__)
manager = TestManager()
maude.init()

def json_check_fn(obtained_filename: Path, expected_filename: Path):
    obtained_str = obtained_filename.read_text()
    obtained_json = json.loads(obtained_str)

    expected_str = expected_filename.read_text()
    expected_json = json.loads(expected_str)

    assert obtained_json == expected_json

@pytest.mark.parametrize(["setup", "cfg"], manager.test_pairs)
def test(file_regression: FileRegressionFixture, setup: Setup, cfg: TestConfig):
    out = maude_runner(setup, **cfg.args)
    file_regression.check(out, extension=".json", check_fn=json_check_fn)