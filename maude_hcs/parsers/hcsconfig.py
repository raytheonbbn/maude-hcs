#!/usr/bin/env python
# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# Maude-HCS Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# The computer software and computer software documentation are licensed
# under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. A copy of the License
# is provided in the LICENSE file, but you may obtain a copy of the
# License at:  https://www.apache.org/licenses/LICENSE-2.0
#
# The computer software and computer software documentation are based
# upon work supported by the Defense Advanced Research Projects Agency (DARPA)
# under Agreement No. HR00l 12590083.
#
# This document does not contain technology or technical data controlled under
# either the U.S. International Traffic in Arms Regulations or the U.S. Export
# Administration Regulations.
#
# DISTRIBUTION STATEMENT A: Approved for public release; distribution is
# unlimited.
#
# Notice: Markings. Any reproduction of this computer software, computer
# software documentation, or portions thereof must also reproduce the markings
# contained herein. Refer to the provided NOTICE file.
#
# MAUDE_HCS: end

import json
from dataclasses import dataclass, field
from typing import List
from pathlib import Path
from dataclasses_json import dataclass_json

from maude_hcs.lib import GLOBALS, Protocol
from maude_hcs.parsers.dnshcsconfig import DNSHCSProtocolConfig
from maude_hcs.parsers.graph import Topology
from maude_hcs.parsers.masdnshcsconfig import MASHCSProtocolConfig
from maude_hcs.parsers.shadowconf import parse_shadow_config
from maude_hcs.parsers.ymlconf import YmlConf
from .protocolconfig import HCSProtocolConfig, Output

@dataclass_json
@dataclass
class HCSConfig:
    """
    An HCS config comprising a set of protocol configurations.
    """
    name: str    
    topology: Topology
    output: Output
    monitor_address: str
    protocols: dict[str, HCSProtocolConfig] # each protocol is keyed by name

    @staticmethod
    def from_shadow(file_path: Path) -> 'DNSHCSConfig':
        """
            TODO: FIXME! (test)
        """
        # First parse the shadow config
        shadowconf = parse_shadow_config(file_path)
        protocols = {}
        dnsconf = DNSHCSProtocolConfig.from_shadow(file_path)
        protocols[dnsconf.name] = dnsconf
        return HCSConfig(name='_'.join(sorted(protocols.keys())),
                        topology=shadowconf.network,
                        output=Output.generic(),
                        monitor_address=GLOBALS.MONITOR_ADDRESS,
                       protocols=protocols)

    @staticmethod
    def from_yml(file_path: Path) -> 'HCSConfig':
        # First parse the yml config
        ymlconf = YmlConf(file_path)
        protocols = {}
        if ymlconf.application.iodine:
            # parse the iodine protocol config
            dnsconf = DNSHCSProtocolConfig.from_yml(file_path)
            protocols[dnsconf.name] = dnsconf
        if ymlconf.application.destini:
            masconf = MASHCSProtocolConfig.from_yml(file_path)
            protocols[masconf.name] = masconf

        return HCSConfig(name='_'.join(sorted(protocols.keys())),
                         topology=ymlconf.network,
                         output=Output.generic(),
                         monitor_address=GLOBALS.MONITOR_ADDRESS,
                         protocols=protocols)


    @staticmethod
    def from_file(file_path: str) -> 'HCSConfig':
        with open(file_path, 'r') as f:
            data = json.load(f)
        hcsconf = HCSConfig.from_dict(data)
        # parse the protocols one at a time
        for k,v in data['protocols'].items():
            hcsconf.protocols[k] = HCSProtocolConfig.load_from_dict(v)
        return hcsconf


    def save(self, file_path: str):
        """
        Exports the dataclass instance to a JSON file.

        Args:
            file_path: The path where the JSON file will be saved.
        """
        with open(file_path, 'w') as f:
            # Convert the dataclass to a dict, then handle the special key name
            data = self.to_dict()
            # data['probabilistic_parameters']['nsResourceBounds?'] = data['probabilistic_parameters'].pop('nsResourceBounds')
            json.dump(data, f, indent=4)