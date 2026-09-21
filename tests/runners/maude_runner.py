import maude
import logging

from pathlib import Path
from argparse import Namespace
from typing import Any

from ..utils.context import BuildConfig, TestConfig, RunConfig
from ..utils.build import build

from maude_hcs.main import handle_command
from maude_hcs.lib import GLOBALS

logger = logging.getLogger(__name__)

def maude_runner(test_cfg: TestConfig, run_cfg: RunConfig) -> str:
    build_dir = build(test_cfg.build_cfg, run_cfg, test_cfg.ctx.directory)
    if run_cfg.build_only: assert(False)

    maude.load(str(build_dir / 'test-env.maude'))
    m: maude.Module = maude.getModule("TEST-ENV")
    t = m.parseTerm(test_cfg.arg)
    t.rewrite()

    return str(t)