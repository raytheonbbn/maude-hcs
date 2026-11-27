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
from ..utils.keys import run_cfg_key

logger = logging.getLogger(__name__)
manager = TestManager()

char_tests = [
    pytest.param(cfg, marks=pytest.mark.runner(cfg.runner))
    for cfg in manager.characterization_test_cfgs()
]

ka_tests = [
    pytest.param(cfg, marks=pytest.mark.runner(cfg.runner))
    for cfg in manager.known_answer_test_cfgs()
]

def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    ids = lambda x: x.mk_id()

    match metafunc.definition.name:
        case "test_characterization":
            metafunc.parametrize("test_cfg", char_tests, ids=ids)

        case "test_known_answer":
            metafunc.parametrize("test_cfg", ka_tests, ids=ids)

        case _:
            raise RuntimeError(f"Unexpected test function name: {metafunc.definition.name}, expected test_characterization or test_known_answer")