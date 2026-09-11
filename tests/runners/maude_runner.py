import maude
import logging
import json
import tempfile
import os
import shutil

from pathlib import Path
from argparse import Namespace

from ..utils.setups import Setup

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

def batch_convert_dir(dir: Path, proto: str):
    """dir should just contain json files representing markov models.
    This function will convert all of them into maude files, placing the results alongside the original jsons.
    """
    markov_args = Namespace(
        verbose=False,
        command='markov',
        markov_command='batch',
        protocol=proto,
        input_dir=str(dir),
        output_dir=str(dir),
    )

    handle_command(markov_args.command, None, markov_args)

def maude_runner(setup: Setup, **kwargs):
    gen_args = kwargs["gen_args"]

    with tempfile.TemporaryDirectory() as tempdir:
        logger.info(f"temp directory created at {tempdir}")
        tempsetup = Path(tempdir) / "setup"
        shutil.copytree(setup.directory, tempsetup)

        for d in kwargs["markov_dirs"]:
            batch_convert_dir(tempsetup / d["path"], d["proto"])

        gen_args = Namespace(
            verbose=False,
            command='generate',
            yaml_file=str(tempsetup / gen_args["yaml_file"]),
            quatex=False,
            baselineTime=gen_args["baseline_time"],
            runTime=gen_args["run_time"],
            hcsDelay=gen_args["hcs_delay"],
            tgenDelay=gen_args["tgen_delay"],
            outDir=str(tempsetup),
            scenarioName='test',
            notgens=gen_args["no_tgens"],
            filterVpFeatCombos=gen_args["filter_vp_feat_combos"],
            filterVpFeatCombos2=gen_args["filter_vp_feat_combos_2"],
            filterVpFeatTop25=gen_args["filter_vp_top_25"],
            filterVpFeatCombo4x5=gen_args["filter_vp_feat_combo_4x5"],
            filterVpFeatIxp=gen_args["filter_vp_feat_ixp"],
            parallelizeBaseline=gen_args["parallelize_baseline"],
            confidentiality=gen_args["confidentiality"],
            perf=gen_args["performance"],
        )

        # TODO: Should capture output and make sure there were no warnings, using contextlib
        handle_command(gen_args.command, None, gen_args)

        with open(tempsetup / 'test-env.maude', 'w') as f:
            f.write(TEST_ENV)

        maude.load(str(tempsetup / 'test-env.maude'))
        m: maude.Module = maude.getModule("TEST-ENV")
        t = m.parseTerm(kwargs["test"])
        t.rewrite()

        d = {"term": str(t)}

        return json.dumps(d, indent=4)