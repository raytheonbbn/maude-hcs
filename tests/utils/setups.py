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
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from typing import Optional, Union

from dataclasses_json import dataclass_json, config

from .utils import read_env_file

logger = logging.getLogger(__name__)

class SetupNotFoundError(Exception):
    def __init__(self, message="A setup could not be find with the provided information."):
        super().__init__(message)

class TestRunner(Enum):
    MAUDE = "MAUDE"
    SMC = "SMC"
    PYTHON = "PYTHON"

@dataclass_json
@dataclass
class TestConfig(object):
    """Defines a configuration for running a specific test within some Setup. So, a completely unambiguous test case can be
    represented with a tuple (Setup, TestConfig)

    Args:
        name (str): A human-readable name for this test. This is used for display and for labeling regression test files
        runner (TestRunner): which python function to use to run the test. This is only an enum identifier for the real function to use.
        args (dict): which args to pass to the runner function for this test. They are passed along with the setup directory.
        regression (bool): Whether to include this test in regression testing
        expected (dict | None): expected value for this test, if not a regression test
    """
    name:       str
    runner:     TestRunner
    regression: bool = False
    expected:   dict | None = None
    args:       dict = field(default_factory=dict)
    __test__ = False

    def __post_init__(self):
        assert self.regression or (self.expected is not None), \
            "a TestConfig must be either a regression test, or contain an expected result"

        assert not (self.regression and (self.expected is not None)), \
            "regression tests use past result files stored by pytest-regression, not json-specified expected values"

@dataclass_json
@dataclass(frozen=True)
class Setup(object):
    """Represents a testing setup in which we can run our actual tests. In particular, self.directory contains the files and context
    we need to run the tests defined by the runargs within that directory.

    Args:
        name (str): A human-readable name for the setup. This is used for display and for labeling regression test files
        directory (str): The directory where the setup resides relative to setups
    """
    name:               str
    directory:          Path

    def get_test_cfgs(self) -> list[TestConfig]:
        cfgs = []

        for root, _, files in os.walk(os.path.join(self.directory, 'test_cfgs')):
            for file in files:
                contents = (Path(root) / file).read_text()
                json_dict = json.loads(contents)
                cfgs.append(TestConfig.from_dict(json_dict)) # type: ignore[attr-defined]
        return cfgs

class TestManager(object):
    __test__ = False

    def __init__(self, directory: Path = Path('./tests/setups'), file: str = 'setups.json'):
        self._setups_directory = directory.resolve()
        self._setups_file = file
        self._setups = self._get_setups()
        self._test_cfgs_by_setup = self._get_test_cfgs_by_setup()

    @property
    def setups(self) -> list[Setup]:
        """ List of all setups"""
        return self._setups

    @property
    def test_cfgs_by_setup(self) -> dict[Setup, list[TestConfig]]:
        return self._test_cfgs_by_setup

    @property
    def test_pairs(self) -> list[tuple[Setup, TestConfig]]:
        return [(setup, cfg) for setup in self.test_cfgs_by_setup for cfg in self.test_cfgs_by_setup[setup]]
    
    def setup_names(self) -> list[str]:
        """ List of all setups"""
        result = [u.name for u in self._setups]
        return result

    @property
    def setups_dir(self) -> Path:
        return self._setups_directory

    @property
    def directories(self) ->list[str]:
        """List of all the known directories in the setup repo"""
        return list(set([str(setup.directory) for setup in self._setups]))

    def _get_test_cfgs_by_setup(self) -> dict[Setup, list[TestConfig]]:
        cfgs = {}
        for setup in self._setups:
            cfgs[setup] = setup.get_test_cfgs()
        return cfgs

    def _get_setups(self) -> list[Setup]:
        setups = []

        with open(self._setups_directory / self._setups_file, 'r') as fio:
            data = json.load(fio)

        for d in data:
            # The json files have relative paths, but it's preferable to work with absolute paths
            d["directory"] = self._setups_directory / d["directory"]
            setups.append(Setup.from_dict(d)) # type: ignore[attr-defined]

        return setups