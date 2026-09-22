import functools
import shutil
import random

from pathlib import Path
from argparse import Namespace

from maude_hcs.main import handle_command
from maude_hcs.lib import GLOBALS

from .context import BuildConfig, RunConfig

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

def batch_convert_dir_v1(dir: Path, proto: str):
    """dir should just contain json files representing markov models.
    This function will convert all of them into maude files, placing the results alongside the original jsons.
    """
    markov_args = Namespace(
        verbose=False,
        command='markov-v1',
        protocol=proto,
        input_dir=str(dir),
        output_dir=str(dir),
    )

    handle_command(markov_args.command, None, markov_args)

def batch_convert_dir_v2(dir: Path, proto: str):
    """dir should just contain json files representing markov models.
    This function will convert all of them into maude files, placing the results alongside the original jsons.
    """
    markov_args = Namespace(
        verbose=False,
        command='markov-v2',
        protocol=proto,
        markov_command='batch',
        input_dir=str(dir),
        output_dir=str(dir),
    )

    handle_command(markov_args.command, None, markov_args)

def build(build_cfg: BuildConfig, run_cfg: RunConfig, src_dir: Path) -> Path:
    gen_args = build_cfg.gen_args
    build_dir = (Path(run_cfg.temp_dir) / f"{build_cfg.name}-{random.randint(0, 10000000)}").resolve()
    shutil.copytree(src_dir, build_dir)

    for dir, proto in build_cfg.markov_v1_dirs:
        batch_convert_dir_v1(build_dir / dir, proto)

    for dir, proto in build_cfg.markov_v2_dirs:
        batch_convert_dir_v2(build_dir / dir, proto)

    args = Namespace(
        verbose=True,
        command='generate',
        yaml_file=str(build_dir / gen_args.yaml_file),
        quatex=True,
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

    with open(build_dir / 'test-env.maude', 'w') as f:
        f.write(TEST_ENV)

    return build_dir