#  BPL Software
#  Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#  Contract No: N6523624C8010
#  Contractor Name: RTX BBN Technologies Inc.
#  Contractor Address: 10 Moulton Street, Cambridge, Massachusetts 02138
#
#  The U.S. Government's rights to use, modify, reproduce, release, perform, display, or disclose these technical data and software are defined in the Rights in Technical Data—Other Than Commercial Products and Commercial Services clause, DFARS 252.227-7013, and the Rights in Other Than Commercial Computer Software and Other Than Commercial Computer Software Documentation clause, DFARS 252.227-7014, contained in the above identified contract.
#
#  WARNING: This document contains technical data and / or technology whose export or disclosure to Non-U.S. Persons, wherever located, is restricted by the International Traffic in Arms Regulations (ITAR) (22 C.F.R. Section 120-130) or the Export Administration Regulations (EAR) (15 C.F.R. Section 730-774). This document CANNOT be exported (e.g., provided to a supplier outside of the United States) or disclosed to a Non-U.S. Person, wherever located, until a final jurisdiction and classification determination has been completed and approved by Raytheon, and any required U.S. Government approvals have been obtained. Violations are subject to severe criminal penalties.
#
#  DISTRIBUTION STATEMENT D: Distribution authorized to Department of Defense and U.S. DoD contractors only (Critical technology), 16 February 2024. Other requests for this document shall be referred to the DARPA Information Innovation Office.
#
#  The U.S. Government retains unlimited data/computer software rights to this item unless this item is identified as technical data or computer software to be furnished with restrictions in the above identified contract.
#  Notice: Markings. Any reproduction of this computer software, computer software documentation, or portions thereof must also reproduce the markings contained herein

import json
import logging
import os

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from dataclasses_json import dataclass_json
from ..runners.maude_runner import maude_runner
from ..runners.smc_runner import smc_runner

logger = logging.getLogger(__name__)

class TestRunner(Enum):
    """Enum to indicate which test runner a TestConfig should use"""
    MAUDE = "maude"
    SMC = "smc"

    __test__ = False

    def to_func(self):
        match self:
            case TestRunner.MAUDE: return maude_runner
            case TestRunner.SMC: return smc_runner
            case _: raise Exception("invalid TestRunner")

@dataclass_json
@dataclass(frozen=True)
class RunConfig:
    """Args for the entire test run, mostly set through command-line args"""
    temp_dir: Path

    runner: TestRunner | None

    regression: bool = False
    expected: bool = False

    log_level: None = None
    log_filter: None = None
    pp: bool = False

    build_only: bool = False
    persist: bool = False

    def __post_init__(self):
        assert not (self.regression and self.expected), "cannot select both regression and expected-value tests for isolation"

@dataclass_json
@dataclass(frozen=True)
class GenArgs:
    yaml_file:      str
    baseline_time:  int
    run_time:       int
    hcs_delay:      int
    tgen_delay:     int
    no_tgens:       bool

    filter_vp_feat_combos:      bool
    filter_vp_feat_combos_2:    bool
    filter_vp_top_25:           bool
    filter_vp_feat_combo_4x5:   bool
    filter_vp_feat_ixp:         bool

    parallelize_baseline:       bool
    confidentiality:            bool
    performance:                bool

@dataclass_json
@dataclass(frozen=True)
class BuildConfig:
    """Contains the arguments we need to generate a full testing environment from a starting context.

    Args:
        name (str): A human-readable name for this config, which is taken directly from the filename
        markov_dirs (list[str]): All the directories that should have their markov json files converted to maude
        gen_args (dict): Arguments for cp3 maude generation
    """

    name: str
    markov_v1_dirs: tuple[tuple[str, str], ...]
    markov_v2_dirs: tuple[tuple[str, str], ...]
    gen_args: GenArgs

@dataclass_json
@dataclass(frozen=True)
class Context:
    """Represents a testing context in which we can run our actual tests. In particular, self.directory contains the files and context
    we need to run the tests defined by the tests.json within that directory.

    Args:
        name (str): A human-readable name for the context. This is used for display and for labeling regression test files
        directory (str): The directory where the context resides relative to <repo_root>/tests/contexts
    """
    name:               str
    directory:          Path

    def _load_test_cfgs_by_runner(self, runner: TestRunner, build_cfgs: dict[str, BuildConfig]) -> list["TestConfig"]:
        test_cfgs = []
        path = self.directory / "tests" / f"{runner.value}.json"
        if path.is_file():
            logger.info(path.read_text())
            tests = json.loads(path.read_text())
            for test in tests:
                assert isinstance(test, dict)
                test_cfgs.append(TestConfig(
                    ctx=self,
                    name=test["name"],
                    desc=test["desc"],
                    expected=test.get("expected", None),
                    runner=runner,
                    build_cfg=build_cfgs[test["build_cfg"]],
                    arg=test.get("arg", {})
                ))
        return test_cfgs

    def get_test_cfgs(self) -> list["TestConfig"]:
        build_cfgs = {}
        test_cfgs = []

        for root, _, files in os.walk(os.path.join(self.directory, 'build_cfgs')):
            for file in files:
                path = Path(root) / file
                d = json.loads(path.read_text())
                build_cfgs[path.stem] = BuildConfig(
                    path.stem,
                    tuple([tuple(l) for l in d["markov_v1_dirs"]]),
                    tuple([tuple(l) for l in d["markov_v2_dirs"]]),
                    GenArgs.from_dict(d["gen_args"]) # type: ignore
                )

        test_cfgs.extend(self._load_test_cfgs_by_runner(TestRunner.MAUDE, build_cfgs))
        test_cfgs.extend(self._load_test_cfgs_by_runner(TestRunner.SMC, build_cfgs))

        return test_cfgs

@dataclass_json
@dataclass
class TestConfig:
    """Defines a configuration for running a specific Maude test (regression or expected) within some Context.

    Args:
        ctx (Context): the Context within which this test is defined
        name (str): A human-readable name for this test. This is used for display and for labeling regression test files
        desc (str): A human-readable description for the purpose and implementation of this test
        runner (TestRunner): which python function to use to run the test.
        build_cfg (dict): args to use when generating markov maude files and the main maude test file
        arg (str): arbitrary object to be passed to the maude runner. Typically includes a predicate or expression to evaluate for the test.
        expected (dict | None): expected value for this test, or None if this is a regression test
    """
    ctx:        Context
    name:       str
    desc:       str 
    runner:     TestRunner
    build_cfg:  BuildConfig
    arg:        Any
    expected:   dict | None = None

    # Prevent pytest from collecting this class
    __test__:   bool = False

class TestManager:
    __test__ = False

    def __init__(self, directory: Path = Path('./tests/contexts')):
        self.contexts_directory = directory.resolve()
        self.contexts = self._get_contexts()
        self.test_cfgs = []

        for ctx in self.contexts:
            self.test_cfgs.extend(ctx.get_test_cfgs())
    
    def regression_test_cfgs(self) -> list[TestConfig]:
        ret = [cfg for cfg in self.test_cfgs if cfg.expected is None]
        return ret

    def expected_test_cfgs(self) -> list[TestConfig]:
        ret = [cfg for cfg in self.test_cfgs if cfg.expected is not None]
        return ret

    def _get_contexts(self) -> list[Context]:
        ctxs = []

        for ctx_dir_name in os.listdir(self.contexts_directory):
            ctx_dir = self.contexts_directory / ctx_dir_name
            if os.path.isdir(ctx_dir):
                if (ctx_dir / "tests").is_dir():
                    ctxs.append(Context(ctx_dir_name, ctx_dir))

        return ctxs
    
def mk_id(val: TestConfig):
    return f"{val.ctx.name}:{val.runner.value}:{val.name}"