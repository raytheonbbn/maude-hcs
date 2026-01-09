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
from dataclasses_json import dataclass_json
from dataclasses_json import DataClassJsonMixin
from maude_hcs.lib import Protocol


# By using `default_factory=dict`, we ensure that a new dictionary is created
# for each instance, preventing mutable default argument issues.

@dataclass_json
@dataclass
class NondeterministicParameters:
    """Dataclass for nondeterministic simulation parameters."""
    other: dict = field(default_factory=dict)

@dataclass_json
@dataclass
class ProbabilisticParameters:
    """Dataclass for probabilistic simulation parameters."""
    other: dict = field(default_factory=dict)

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

@dataclass
class BackgroundTraffic(DataClassJsonMixin):
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

    @staticmethod
    def generic():
        out = Output()
        out.force_save = True
        out.preamble = [
            "set clear rules off .",
            "set print attribute off .",
            "set show advisories off ."
        ]
        return out

@dataclass
class BackgroundTrafficTgenClient(DataClassJsonMixin):
    """Dataclass for background traffic parameters."""
    client_name: str = ''
    client_markov_model_profile: str = ''
    start_time: float = 0.0

@dataclass
class DNSBackgroundTrafficTgenClient(BackgroundTrafficTgenClient):
    """Dataclass for background traffic parameters."""
    client_retry_to: float = 0.0
    client_num_retry: int = 1

@dataclass
class MASBackgroundTrafficTgenClient(BackgroundTrafficTgenClient):
    """Dataclass for background traffic parameters."""
    client_username: str = ''
    clients_images_dir: str = ''
    client_hashtags: list[str] = field(default_factory=list)

@dataclass
class BackgroundTrafficTgen(DataClassJsonMixin):
    """Dataclass for background traffic parameters."""
    module: str
    num_clients: int
    clients: list[BackgroundTrafficTgenClient]

    @classmethod
    def from_dict(cls, kvs, **kwargs):
        # 1. Extract the discriminator
        proto = kvs['module']
        CLS = []
        for client in kvs['clients']:
            if proto == Protocol.DNS.value:
                CLS.append(DNSBackgroundTrafficTgenClient.from_dict(client, **kwargs))
            elif proto == Protocol.MASTODON.value:
                CLS.append(MASBackgroundTrafficTgenClient.from_dict(client, **kwargs))
        bg = super().from_dict(kvs, **kwargs)
        bg.clients = CLS
        return bg

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
class XFile:
    id: int = 0
    size_bytes : int = 1

    def to_maude(self):
        return f'file({self.id}, {self.size_bytes})'

def files_to_maude(files:list[XFile]):
    return ' :: '.join(x.to_maude() for x in files)

@dataclass_json
@dataclass
class DuplexApplication(Application):
    module: str = 'duplex'
    alice_address: str = ''
    bob_address: str = ''
    hashtags: list[str] = field(default_factory=list)
    xfiles : list[XFile] = field(default_factory=list)

@dataclass
class HCSProtocolConfig(DataClassJsonMixin):
    """
    Dataclass for HCS protocol configuration
    """
    name: str = Protocol.NA.value
    underlying_network: UnderlyingNetwork = None
    weird_network: WeirdNetwork = None
    application: Application = None
    background_traffic: BackgroundTrafficTgen = None
    nondeterministic_parameters: NondeterministicParameters = field(default_factory=dict)
    probabilistic_parameters: ProbabilisticParameters = field(default_factory=dict)

    @classmethod
    def load_from_dict(cls, kvs, **kwargs):
        """
        Override to detect the protocol_type and delegate
        to the specific subclass.
        """
        # Standard behavior for leaf classes or if no discriminator found
        if cls is HCSProtocolConfig:
            # Check if we are calling this specifically on the Base class
            #    and if the dictionary has our discriminator field.
            #
            target_type = kvs['name']

            # 2. Search all known subclasses for a match
            for subclass in HCSProtocolConfig.__subclasses__():
                if subclass.name == target_type:
                    # 3. Delegate to the subclass's from_dict (standard behavior)
                    CLS = subclass.from_dict(kvs, **kwargs)
                    bgT = BackgroundTrafficTgen.from_dict(kvs['background_traffic'], **kwargs)
                    CLS.background_traffic = bgT
                    return CLS

            # Optional: Raise error if type is unknown
            raise ValueError(f"Unknown protocol_type: {target_type}, no subclass matching {target_type} in {HCSProtocolConfig.__subclasses__()}")

        return super().from_dict(kvs, **kwargs)