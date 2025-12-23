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
from pathlib import Path
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from numpy.ma.core import floor

from maude_hcs.parsers.markovJsonToMaudeParser import find_and_load_json
from .dnshcsconfig import DNSHCSConfig
from .hcsconfig import Application, BackgroundTraffic, HCSConfig, NondeterministicParameters, Output, \
    ProbabilisticParameters, UnderlyingNetwork, WeirdNetwork, BackgroundTrafficTgen, BackgroundTrafficTgenClient, \
    Tunnel, DuplexApplication
from .ymlconf import YmlConf
from maude_hcs import  PROJECT_TOPLEVEL_DIR

@dataclass_json
@dataclass
class MASUnderlyingNetwork(UnderlyingNetwork):
    module: str = 'mastodon'
    # mastodon server fqdn (this is DNS related)
    mastodon_fqdn: str = ''
    mastodon_address: str = ''
    # router
    router: str                         = 'router'


@dataclass_json
@dataclass
class MASBackgroundTrafficTgenClient(BackgroundTrafficTgenClient):
    """Dataclass for background traffic parameters."""
    client_username: str = ''
    clients_images_dir: str = ''
    client_hashtags: list[str] = field(default_factory=list)

@dataclass_json
@dataclass
class MASWeirdNetwork(Tunnel):
    alice_raceboat_profile: str = ''
    bob_raceboat_profile: str = ''

    @staticmethod
    def fromTunnel(tunnel: Tunnel) -> 'MASWeirdNetwork':
        return MASWeirdNetwork(
            module=tunnel.module,
            send_app_address=tunnel.send_app_address,
            rcv_app_address=tunnel.rcv_app_address,
            tunnel_client_addr=tunnel.tunnel_client_addr,
            tunnel_server_addr=tunnel.tunnel_server_addr,
            sender_northbound_addr=tunnel.sender_northbound_addr,
            receiver_northbound_addr=tunnel.receiver_northbound_addr
        )
'''
This is the configuration for CP2
'''
@dataclass_json
@dataclass
class MASHCSConfig(HCSConfig):
    underlying_network: UnderlyingNetwork
    weird_network: MASWeirdNetwork
    application: DuplexApplication
    background_traffic: BackgroundTrafficTgen
    nondeterministic_parameters: NondeterministicParameters
    probabilistic_parameters: ProbabilisticParameters

    @staticmethod
    def from_file(file_path: str) -> 'MASHCSConfig':
        with open(file_path, 'r') as f:
            data = json.load(f)
        return MASHCSConfig.from_dict(data)

    @staticmethod
    def from_yml(file_path: Path) -> 'MASHCSConfig':
        # First parse the yml config
        ymlconf = YmlConf(file_path)
        alice = ymlconf.network.getNodebyLabel('user_alice')
        if alice is None:
            alice = ymlconf.application.alice.mastodon_user
        else:
            alice = alice.label
        bob = ymlconf.network.getNodebyLabel('user_bob').label
        # application
        app = DuplexApplication()
        app.alice_address = alice
        app.bob_address = bob

        m_un = MASUnderlyingNetwork()
        m_un.module = 'mastodon'
        m_un.mastodon_fqdn = ymlconf.underlying_network.server_fqdn
        m_un.mastodon_address = ymlconf.underlying_network.server_address
        # verify mastodon address is in the nodes or use the latter
        if not ymlconf.network.getNodebyLabel(m_un.mastodon_address):
            # does there exist a node that starts with mastodon?
            if ymlconf.network.getNodebyLabel('mastodon'):
                m_un.mastodon_address = ymlconf.network.getNodebyLabel('mastodon').label
            else:
                raise Exception('mastodon server address not found in network')

        # > now the weird nets
        tun = Tunnel()
        tun.receiver_northbound_addr = app.bob_address
        tun.sender_northbound_addr = app.alice_address
        mas_wn = MASWeirdNetwork.fromTunnel(tun)
        mas_wn.module = 'mastodon'
        mas_wn.send_app_address = f'{app.alice_address}-mas-snd-app'
        mas_wn.rcv_app_address = f'{bob}-mas-rcv-app'
        mas_wn.tunnel_client_addr = f'{app.alice_address}-raceboat-client'
        mas_wn.tunnel_server_addr = f'{app.alice_address}-raceboat-server'
        mas_wn.alice_raceboat_profife = ymlconf.application.alice.raceboat_prof
        mas_wn.bob_raceboat_profife = ymlconf.application.bob.raceboat_prof

        # > bg
        i = 0
        bg = BackgroundTrafficTgen()
        for (type, json_prof, cnt) in ymlconf.background_traffic:
            if cnt == 0: continue
            if 'monitor' in type: continue
            for j in range(cnt):
                if type == 'mastodon':
                    C = MASBackgroundTrafficTgenClient()
                    C.client_name = f'mas-tgen-client-{(i+j)}'
                    # this converts it to an importable module name
                    C.client_markov_model_profile =  "mas-" + json_prof.replace(".json","").replace("_", "-")
                    # search for the json_prof file and grab the parameters dict
                    # use that to set the retry and lifetime
                    # we have already copied the json file to the right directory in maude_hcs, find it
                    data = find_and_load_json(PROJECT_TOPLEVEL_DIR, json_prof)
                    C.client_hashtags = data['parameters']['hashtags']
                    C.client_username = data['parameters']['username']
                    C.clients_images_dir = data['parameters']['image_repo']
                    bg.clients.append(C)
            i = i + j + 1
        bg.num_clients = len(bg.clients)

        out = Output()
        out.force_save = True
        out.preamble = [
            "set clear rules off .",
            "set print attribute off .",
            "set show advisories off ."
        ]
        return MASDNSHCSConfig(name='corporate_iodine_mastodon',
                            topology=ymlconf.network,
                            output=out,
                            underlying_network=m_un,
                            weird_network=mas_wn,
                            application=app,
                            background_traffic=bg,
                            nondeterministic_parameters=ndp,
                            probabilistic_parameters=pp,
                            monitor_address = 'monAddr')