from dataclasses import replace
from pathlib import Path
import tempfile
import os

import maude
import pyperclip
import pytest

from maude_hcs.lib import GLOBALS

from ..utils.single_tgens import load_suite, run_suite, Case, CaseStatus, SingleTgenExperiment
from ..utils.context import TestConfig, Context, TestRunner, RunConfig
from ..utils.keys import run_cfg_key

CTX_PATH = GLOBALS.TOP_LEVEL_DIR / "tests" / "contexts" / "confidentiality"

if __name__ == "__main__":

    run_cfg = RunConfig(
        temp_dir=Path(tempfile.mkdtemp()).resolve(),
        runner=None,

        composition=False,
        characterization=False,
        known_answer=False,

        build_only=False,
        persist=True,
        results_dir=None,

        override_run_time=None,
        timeout=None,
        partial_smc_comp=False,
    )

    pyperclip.copy(str(run_cfg.temp_dir))

    exp_strs = [
        "dns",
        "ftp_obfs",
        "ftp_webtunnel",
        "gorilla_obfs",
        "gorilla_webtunnel",
        "irc_obfs",
        "irc_webtunnel",
        "mastodon",
        "minio",
    ]

    suite = []

    for exp_str in exp_strs:
        exp = SingleTgenExperiment(
            ctx_path=CTX_PATH,
            name=f"single_tgen_{exp_str}",
            yaml=f"single_tgens/{exp_str}.yaml",
            feats=[
                "dnsQueryRate",
                "dnsQuerySize",
                "dnsRespSize",
                "tcpUpRate",
                "tcpDownRate",
                "tcpUpToDownRate",
                "tcpOutPktRate",
                "tcpInPktRate",
                "tcpOutToInPktRate",
                "tcpPktSizeStdDev",
                "tcpPktSize",
                "tcpPktInterarrival",
                "tcpDirectionChange",
                "tcpActiveFlow",
                "tcpNewCnx"
            ],
            vantages=[
                "ixpN",
                "srvN",
                "minN",
                "masN",
                "dnsN",
                "cl[1]",
                "cl[2]",
                "cl[3]",
                "cl[4]",
                "cl[5]"
            ],
            window_sizes=[600],
        )
        suite.append(exp)

    run_suite(suite, run_cfg, False)