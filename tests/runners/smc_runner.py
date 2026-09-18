import logging
import json

from pathlib import Path
from argparse import Namespace

from ..utils.context import BuildConfig, TestConfig, RunConfig
from ..utils.build import build

from maude_hcs.main import run_scheck
from maude_hcs.lib import GLOBALS

logger = logging.getLogger(__name__)

def smc_runner(test_cfg: TestConfig, run_cfg: RunConfig) -> dict:
    build_dir = build(test_cfg.build_cfg, run_cfg, test_cfg.ctx.directory)
    run_file = f"test-run-{test_cfg.build_cfg.gen_args.run_time}.maude"
    arg = test_cfg.arg

    args = Namespace(

        # Configurable by test
        file=str((GLOBALS.TOP_LEVEL_DIR / arg.get("file", "maude_hcs/lib/smc/smc_cp3.maude")).resolve()),
        nsims=arg.get("nsims", "1-1"),
        seed=arg.get("seed", 0),
        jobs=arg.get("jobs", 1),
        D=arg.get("D", None),
        assign=arg.get("assign", "pmaude"),
        alpha=arg.get("alpha", 0.05),
        delta=arg.get("delta", 0.5),
        block=arg.get("block", 30),
        distribute=arg.get("distribute", False),

        # Configurable, but I think it's unlikely we'd want to
        advise=arg.get("advise", True),
        module=arg.get("module", None),
        metamodule=arg.get("metamodule", None),
        strategy=arg.get("strategy", None),
        opaque=arg.get("opaque", ""),
        full_matchrew=arg.get("full_matchrew", None),

        # Not configurable, either no real reason to configure or doing so would break framework
        dump=str(build_dir / "dump.json"),
        test=str(build_dir / run_file),
        query=str(build_dir / "test.quatex"),
        initial="initConfig",
        format="json",
        plot=False,
        verbose=False,
    )

    (out, _) = run_scheck(args, init_maude=False)
    logger.info(out)
    return json.loads(out)