import maude
import logging
import json
import tempfile
import os
import shutil
import contextlib
import io
import pytest
import functools

from pathlib import Path
from argparse import Namespace

from ..utils.context import BuildConfig, TestConfig

from maude_hcs.main import handle_command
from maude_hcs.lib import GLOBALS

logger = logging.getLogger(__name__)

# We just need this so we can have a module to execute tests in where both TEST and TEST-UTILS are available,
# without having TEST directly include TEST-UTILS or vice versa (which would be impossible in this setup)
TEST_ENV = f"""
sload ./test.maude
sload {GLOBALS.LIB_DIR}/test-utils/test-utils.maude

mod TEST-ENV is
  inc TEST .
  inc TEST-UTILS .
endm
"""

# class Build:
#     def __init__(self, dir: str, module):
#         self.dir = dir
#         self.module = module


def batch_convert_dir(dir: Path, proto: str):
    """dir should just contain json files representing markov models.
    This function will convert all of them into maude files, placing the results alongside the original jsons.
    """
    markov_args = Namespace(
        verbose=False,
        command='markov',
        protocol=proto,
        markov_command='batch',
        input_dir=str(dir),
        output_dir=str(dir),
    )

    handle_command(markov_args.command, None, markov_args)

@functools.cache
def build_module(build_cfg: BuildConfig, src_dir: Path, temp_dir: Path) -> Path:
    gen_args = build_cfg.gen_args
    build_dir = (Path(temp_dir) / build_cfg.name).resolve()
    shutil.copytree(src_dir, build_dir)

    for dir, proto in build_cfg.markov_dirs:
        batch_convert_dir(build_dir / dir, proto)

    args = Namespace(
        verbose=True,
        command='generate',
        yaml_file=str(build_dir / gen_args.yaml_file),
        quatex=False,
        baselineTime=gen_args.baseline_time,
        runTime=gen_args.run_time,
        hcsDelay=gen_args.hcs_delay,
        tgenDelay=gen_args.tgen_delay,
        outDir=str(build_dir),
        scenarioName='test',
        notgens=gen_args.no_tgens,
        filterVpFeatCombos=gen_args.filter_vp_feat_combos,
        filterVpFeatCombos2=gen_args.filter_vp_feat_combos_2,
        filterVpFeatTop25=gen_args.filter_vp_top_25,
        filterVpFeatCombo4x5=gen_args.filter_vp_feat_combo_4x5,
        filterVpFeatIxp=gen_args.filter_vp_feat_ixp,
        parallelizeBaseline=gen_args.parallelize_baseline,
        confidentiality=gen_args.confidentiality,
        perf=gen_args.performance,
    )

    handle_command(args.command, None, args)
    return build_dir

def regression_maude_runner(cfg: TestConfig, temp_dir: Path):
    build_dir = build_module(cfg.build_cfg, cfg.ctx.directory, temp_dir)

    with open(build_dir / 'test-env.maude', 'w') as f:
        f.write(TEST_ENV)

    maude.load(str(build_dir / 'test-env.maude'))
    m: maude.Module = maude.getModule("TEST-ENV")
    t = m.parseTerm(cfg.arg)
    t.rewrite()

    d = {"term": str(t)}

    return json.dumps(d, indent=4)