import maude
import logging

from pathlib import Path
from typing import TYPE_CHECKING

# prevents circular import
if TYPE_CHECKING:
    from ..utils.context import TestConfig, RunConfig

logger = logging.getLogger(__name__)

def maude_runner(test_cfg: "TestConfig", build_dir: Path, run_cfg: "RunConfig") -> str:
    maude.init()
    maude.load(str(build_dir / 'test-env.maude'))
    m: maude.Module = maude.getModule("TEST-ENV")
    t = m.parseTerm(test_cfg.arg)
    t.rewrite()
    return str(t)