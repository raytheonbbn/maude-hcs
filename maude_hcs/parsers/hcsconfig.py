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

from maude_hcs.parsers.graph import Topology
from maude_hcs.parsers.shadowconf import parse_shadow_config


# By using `default_factory=dict`, we ensure that a new dictionary is created
# for each instance, preventing mutable default argument issues.

@dataclass_json
@dataclass
class NondeterministicParameters:
    """Dataclass for nondeterministic simulation parameters."""
    pass

@dataclass_json
@dataclass
class ProbabilisticParameters:
    """Dataclass for probabilistic simulation parameters."""
    pass

@dataclass_json
@dataclass
class UnderlyingNetwork:
    """Dataclass for the underlying network configuration."""
    module: str


@dataclass_json
@dataclass
class WeirdNetwork:
    """Dataclass for the 'weird' (covert) network configuration."""
    module: str

@dataclass_json
@dataclass
class BackgroundTraffic:
    """Dataclass for background traffic parameters."""
    module: str

@dataclass_json
@dataclass
class Application:
    """Dataclass for the application layer configuration."""
    module: str

@dataclass_json
@dataclass
class Output:
    """Dataclass for output and reporting settings."""
    directory: str = "./results"
    result_format: str = "maude"
    save_output: bool = True
    force_save: bool = False
    visualize: bool = False
    preamble: List[str]     = field(default_factory=list)

@dataclass_json
@dataclass
class BackgroundTrafficTgenClient():
    """Dataclass for background traffic parameters."""
    client_name: str = ''
    client_markov_model_profile: str = ''
    start_time: float = 0.0

@dataclass_json
@dataclass
class BackgroundTrafficTgen(BackgroundTraffic):
    """Dataclass for background traffic parameters."""
    module: str = 'dns'
    num_clients: int = 1
    clients: list[BackgroundTrafficTgenClient] = field(default_factory=list)

@dataclass_json
@dataclass
class Tunnel(WeirdNetwork):
    module: str = 'NA'
    send_app_address: str   = ''
    rcv_app_address: str    = ''
    tunnel_client_addr: str = ''
    tunnel_server_addr: str = ''
    sender_northbound_addr: str = '' # who does sndapp get info from
    receiver_northbound_addr: str = '' # who does rcvApp send info to

@dataclass_json
@dataclass
class DuplexApplication(Application):
    module: str = 'NA'
    alice_address: str = ''
    bob_address: str = ''

@dataclass_json
@dataclass
class HCSProtocolConfig:
    """
    Dataclass for HCS protocol configuration
    """
    name: str
    underlying_network: UnderlyingNetwork
    weird_network: WeirdNetwork
    application: Application
    background_traffic: BackgroundTraffic
    nondeterministic_parameters: NondeterministicParameters
    probabilistic_parameters: ProbabilisticParameters

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
    def from_file(file_path: str) -> 'HCSConfig':
        with open(file_path, 'r') as f:
            data = json.load(f)
        return HCSConfig.from_dict(data)

    @staticmethod
    def from_shadow(file_path: Path) -> 'DNSHCSConfig':
        # First parse the shadow config
        shadowconf = parse_shadow_config(file_path)


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