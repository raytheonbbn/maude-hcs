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
import os
from pathlib import Path
from typing import List
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from numpy.ma.core import floor

from maude_hcs.parsers.shadowconf import parse_shadow_config
from maude_hcs.parsers.markovJsonToMaudeParser import find_and_load_json
from .hcsconfig import Application, BackgroundTraffic, HCSConfig, NondeterministicParameters, Output, ProbabilisticParameters, UnderlyingNetwork, WeirdNetwork
from . import load_yaml_to_dict
from .ymlconf import YmlConf
from maude_hcs import  PROJECT_TOPLEVEL_DIR

QPS = {
    'low': 15,
    'medium': 30,
    'high':50
}

@dataclass_json
@dataclass
class DNSUnderlyingNetwork(UnderlyingNetwork):    
    module: str                         = 'dns'
    root_name: str                      = 'root'
    tld_name:  str                      = 'tld'
    tld_domain: str                     = 'com.'
    resolver_name: str                  = ''
    corporate_name: str                 = ''
    corporate_domain: str               = 'corporate.com.'
    everythingelse_name: str            = ''
    everythingelse_domain: str          = 'internet.com.'
    everythingelse_num_records: int     = 1
    pwnd2_name: str                     = ''
    pwnd2_domain: str                   = ''
    populate_resolver_cache: bool       = True
    addr_prefix: str                    = 'addr-'
    # TTL for authoritative non-NS 'A' names; disables caching of queries 
    record_ttl_a: int                   = 0
    # TTL for all other records
    record_ttl: int                     = 3600
    # router
    router: str                         = 'router'
    
@dataclass_json
@dataclass
class DNSWeirdNetwork(WeirdNetwork):
    """Dataclass for the 'weird' (covert) network configuration."""
    module: str = 'iodine'
    client_name: str = ''
    client_weird_qtype: str = ''
    severWResponseTTL: float = 0.0
    monitor_address: str = 'addrMon'

@dataclass_json
@dataclass
class DNSNondeterministicParameters(NondeterministicParameters):
    """Dataclass for nondeterministic simulation parameters."""
    fileSize: int = 100
    packetSize: int = 1
    packetOverhead: int = 1
    maxMinimiseCount: int = 0
    maxFragmentLen: int = 1
    maxFragmentTx: int = 1

@dataclass_json
@dataclass
class DNSProbabilisticParameters(ProbabilisticParameters):
    """Dataclass for probabilistic simulation parameters."""
    maxPacketSize: int = 1
    pacingTimeoutDelay: float = 0.0
    pacingTimeoutDelayMax: float = 0.0
    ackTimeoutDelay: float = 0.0

@dataclass_json
@dataclass
class DNSNondeterministicParameters2(NondeterministicParameters):
    packetOverhead: int = 1
    maxMinimiseCount: int = 0
    maxFragmentLen: int = 1
    maxFragmentTx: int = 1
    maxResponseLen: int = 1

@dataclass_json
@dataclass
class DNSProbabilisticParameters2(ProbabilisticParameters):
    ackTimeoutDelay: float = 1.0
    pingInterval: float = 1.0
    initialPingDelay: float = 0.001
    receiveToPingDelay: float = 0.001

@dataclass_json
@dataclass
class DNSBackgroundTraffic(BackgroundTraffic):
    """Dataclass for background traffic parameters."""    
    module: str = 'dns'
    num_paced_clients: int = 1
    paced_client_name: str = ''
    paced_client_Tlimit: int = 1
    paced_client_MaxQPS: int = 1

@dataclass_json
@dataclass
class DNSBackgroundTrafficTgenClient():
    """Dataclass for background traffic parameters."""
    client_name: str = ''
    client_retry_to: float = 0.0
    client_num_retry: int = 1
    client_markov_model_profile: str = ''
    start_time: float = 0.0

@dataclass_json
@dataclass
class DNSBackgroundTrafficTgen(BackgroundTraffic):
    """Dataclass for background traffic parameters."""
    module: str = 'dns'
    num_clients: int = 1
    clients: list[DNSBackgroundTrafficTgenClient] = field(default_factory=list)


@dataclass_json
@dataclass
class SimplexApplication(Application):
    """Dataclass for the application layer configuration."""
    module: str = 'iodine'
    send_app_address: str   = ''
    overwrite_queue: bool   = True
    send_app_queue_pkt_sizes: List[int] = field(default_factory=list)
    app_start_send_time: float = 0.0
    rcv_app_address: str    = ''
    include_dns_client: bool    = False

@dataclass_json
@dataclass
class DuplexApplication(Application):
    """Dataclass for the application layer configuration."""
    module: str = 'iodine'
    send_app_address: str   = ''
    rcv_app_address: str    = ''
    tunnel_client_addr: str = ''
    tunnel_server_addr: str = ''
    sender_northbound_addr: str = '' # who does sndapp get info from
    receiver_northbound_addr: str = '' # who does rcvApp send info to

@dataclass_json
@dataclass
class DNSHCSConfig(HCSConfig):
    underlying_network: DNSUnderlyingNetwork
    weird_network: DNSWeirdNetwork
    application: SimplexApplication
    background_traffic: DNSBackgroundTraffic
    nondeterministic_parameters: DNSNondeterministicParameters
    probabilistic_parameters: DNSProbabilisticParameters

    @staticmethod
    def from_file(file_path: str) -> 'DNSHCSConfig':
        with open(file_path, 'r') as f:
            data = json.load(f)
        return DNSHCSConfig.from_dict(data)

    @staticmethod
    def from_shadow(file_path: Path) -> 'DNSHCSConfig':
        # First parse the shadow config
        shadowconf = parse_shadow_config(file_path)
        # Then create the HCS config one object at a time
        un = DNSUnderlyingNetwork()
        un.module = 'dns'
        un.root_name = shadowconf.network.getNodebyLabel('root').label
        un.tld_name = shadowconf.network.getNodebyLabel('tld').label
        un.tld_domain = 'com.' # TODO parse zome files??
        un.resolver_name = shadowconf.network.getNodebyLabel('public-dns').label
        un.corporate_name = shadowconf.network.getNodebyLabel('local-dns').label
        un.corporate_domain = 'corporate.com.' # TODO parse zome files??
        un.everythingelse_name = shadowconf.network.getNodebyLabel('internet-dns').label
        un.everythingelse_domain = 'internet.com.' # TODO parse zome files??
        un.everythingelse_num_records = 1
        un.pwnd2_name = shadowconf.network.getNodebyLabel('application-server').label
        #un.pwnd2_domain = shadowconf.hosts['application_server'].getProcessByPName('iodined').args[-1]
        un.pwnd2_domain = "pwnd.com."
        un.populate_resolver_cache = True        
        un.record_ttl_a = 0
        un.record_ttl = 3600
        # > now the weird net
        wn = DNSWeirdNetwork()
        wn.module = 'dns'
        wn.client_name = 'application-client'
        wn.client_weird_qtype = 'a'
        wn.severWResponseTTL = 0.0 # where do we get this from??
        wn.monitor_address = 'monAddr'
        app = SimplexApplication()
        app.module = 'simplex'
        app.send_app_address   = 'Alice'
        app.overwrite_queue   = True
        app.app_start_send_time = 1.0 # is this defined somewhere?
        app.rcv_app_address = 'Bob'
        app.include_dns_client  = False
        # > bg
        bg = DNSBackgroundTraffic()
        bg.num_paced_clients = 1 # can probably get this from yaml?
        bg.paced_client_name = 'dnsperf'
        bg.paced_client_Tlimit = int(shadowconf.hosts['dnsperf'].getProcessByPName('./dnsperf_profiles.sh').args[-1])
        bg.paced_client_MaxQPS = QPS[shadowconf.hosts['dnsperf'].getProcessByPName('./dnsperf_profiles.sh').args[-2]]
        # > nondeterministic params
        ndp = DNSNondeterministicParameters()
        # args: "python3 src/cp1_client.py -f data/input/large.dat -l data/logs/ -c 1 -a application_profiles/medium_static.yaml -m 1024 -s 42"
        def _fz(s:str):
            if 'small' in s: return 100
            if 'medium' in s: return 1000
            if 'large' in s: return 10000       
        ndp.fileSize = _fz(shadowconf.hosts['application_client'].getProcessByPName('python3').args[3])
        # > Read `packetSize` and `maxPacketSize` from `chunk_size_min` and `chunk_size_max`, applied as a percentage of the MTU size (passed by the `-m` argument on the Iodine command line) in the send application profile's yaml file.
        # TODO path to app yaml file needs a consistent way to get to
        print(f'>>>>>>>> {file_path}')
        app_params = load_yaml_to_dict(file_path.parent.parent.parent.joinpath('application').joinpath(shadowconf.hosts['application_client'].getProcessByPName('python3').args[9]))
        assert shadowconf.hosts['application_client'].getProcessByPName('python3').args[10] == "-m", 'expected -m instead'
        mtu = int(shadowconf.hosts['application_client'].getProcessByPName('python3').args[11])
        ndp.packetOverhead = 33
        ndp.packetSize = int((app_params['chunk_size_min']/100)*mtu) - ndp.packetOverhead
        assert ndp.packetSize > 0
        # > Read the pacing timeout values from `chunk_spacing_min` and `chunk_spacing_max` in the send application profile's yaml file.
        ndp.maxMinimiseCount = 0
        # > Read the maximum fragment length from the maximum DNS request length limit (passed by the `-M` argument on the Iodine command line) and per-query overhead (currently unknown).
        assert shadowconf.hosts['application_client'].getProcessByPName('iodine').args[2] == "-M"
        ndp.maxFragmentLen = int(shadowconf.hosts['application_client'].getProcessByPName('iodine').args[3]) - 2
        # Change this number if different codec is desired:
        # 18.72% for Base128
        # 37.22% for Base64
        # Base32 is likely around 60%
        codec_overhead = 0.1872
        # Not all maxFragmentLen, specified by -M flag, is usable for the payload.  Based on current understanding of Iodine overhead (+3B) encoded + 12B non encoded:
        # Payload_size  = (hostname_len - 12 - 3 x (1 + 0.1872)) / (1 + 0.1872)
        ndp.maxFragmentLen = round((ndp.maxFragmentLen - 12 - 3 * (1 + codec_overhead)) / (1 + codec_overhead))
        ndp.maxFragmentTx = 20
        pp = DNSProbabilisticParameters()
        pp.maxPacketSize = int((app_params['chunk_size_max']/100)*mtu) - ndp.packetOverhead
        pp.pacingTimeoutDelay = float(app_params['chunk_spacing_min'])
        pp.pacingTimeoutDelayMax = float(app_params['chunk_spacing_max'])
        pp.ackTimeoutDelay = 1.0
        out = Output()
        out.force_save = True
        out.preamble = [
            "set clear rules off .",
            "set print attribute off .",
            "set show advisories off ."
        ]
        return DNSHCSConfig(name='corporate_iodine',
                            topology=shadowconf.network,
                            output=out,
                            underlying_network=un,
                            weird_network=wn,
                            application=app,
                            background_traffic=bg,
                            nondeterministic_parameters=ndp,
                            probabilistic_parameters=pp)
'''
This is the configuration for CP2
'''
@dataclass_json
@dataclass
class DNSHCSConfig2(HCSConfig):
    underlying_network: DNSUnderlyingNetwork
    weird_network: DNSWeirdNetwork
    application: DuplexApplication
    background_traffic: DNSBackgroundTrafficTgen
    nondeterministic_parameters: DNSNondeterministicParameters2
    probabilistic_parameters: DNSProbabilisticParameters2

    @staticmethod
    def from_file(file_path: str) -> 'DNSHCSConfig2':
        with open(file_path, 'r') as f:
            data = json.load(f)
        return DNSHCSConfig2.from_dict(data)

    @staticmethod
    def from_yml(file_path: Path) -> 'DNSHCSConfig2':
        # First parse the yml config
        ymlconf = YmlConf(file_path)
        alice = ymlconf.network.getNodebyLabel('user_alice')
        if alice is None:
            alice = 'user_alice'
        else:
            alice = alice.label
        bob = ymlconf.network.getNodebyLabel('user_bob').label
        # Then create the HCS config one object at a time
        un = DNSUnderlyingNetwork()
        un.module = 'dns'
        un.root_name = ymlconf.network.getNodebyLabel('root').label
        un.tld_name = ymlconf.network.getNodebyLabel('tld').label
        un.tld_domain = 'com.' # TODO parse zome files??
        un.resolver_name = ymlconf.network.getNodebyLabel('public_dns').label
        # the router and the corp dns domain
        un.router = un.corporate_name = ymlconf.network.getNodebyLabel('router').label
        un.corporate_name = 'corporate_dns'
        un.corporate_domain = 'corporate.com.' # TODO parse zome files??
        # this is the auth server for pwnd.com also (and all other domains on internet)
        un.everythingelse_name = ymlconf.network.getNodebyLabel('auth_dns').label
        un.everythingelse_domain = 'internet.com.' # TODO parse zome files??
        un.everythingelse_num_records = 1
        #un.pwnd2_name = ymlconf.network.getNodebyLabel('application-server').label
        # this sits inside Bob
        # this is really t1.pwnd.com but unimportant details for our purposes
        un.pwnd2_name = f'{bob}-iodine-server'
        un.pwnd2_domain = "pwnd.com."
        un.populate_resolver_cache = True
        un.record_ttl_a = 0
        un.record_ttl = 3600
        # > now the weird net
        wn = DNSWeirdNetwork()
        wn.module = 'dns'
        wn.client_name = f'{alice}-iodine-client'
        wn.client_weird_qtype = 'a'
        wn.severWResponseTTL = 0.0 # where do we get this from??
        wn.monitor_address = 'monAddr'
        app = DuplexApplication()
        app.module = 'iodine_duplex'
        app.send_app_address   = f'{alice}-iodine-snd-app'
        app.rcv_app_address = f'{bob}-iodine-rcv-app'
        app.tunnel_client_addr = wn.client_name
        app.tunnel_server_addr = un.pwnd2_name
        app.receiver_northbound_addr = bob
        app.sender_northbound_addr = alice

        # > bg
        i = 0
        bg = DNSBackgroundTrafficTgen()
        for (type, json_prof, cnt) in ymlconf.background_traffic:
            if cnt == 0: continue
            if 'monitor' in type: continue
            if not type == 'dns': continue
            for j in range(cnt):
                C = DNSBackgroundTrafficTgenClient()
                C.client_name = f'dns-tgen-client-{(i+j)}'
                # this converts it to an importable module name
                C.client_markov_model_profile =  "dns-" + json_prof.replace(".json","").replace("_", "-")
                # search for the json_prof file and grab the parameters dict
                # use that to set the retry and lifetime
                # we have already copied the json file to the right directory in maude_hcs, find it
                data = find_and_load_json(PROJECT_TOPLEVEL_DIR, json_prof)
                C.client_retry_to = float(data['parameters']['request_timeout'])
                C.client_num_retry = floor(int(data['parameters']['request_lifetime']) / C.client_retry_to)
                bg.clients.append(C)
            i = i + j + 1
        bg.num_clients = len(bg.clients)

        # > nondeterministic params
        ndp = DNSNondeterministicParameters2()
        # TODO parse the file metadata Alice is sending, for each file its size in order
        ndp.maxMinimiseCount = 0
        # > Read the maximum fragment length from the maximum DNS request length limit (passed by the `-M` argument on the Iodine command line) and per-query overhead (currently unknown).
        # TODO I dont recall why the -2?
        ndp.maxFragmentLen = ymlconf.application.iodine.max_query_length - 2
        # Change this number if different codec is desired:
        # 18.72% for Base128
        # 37.22% for Base64
        # Base32 is likely around 60%
        codec_overhead = 0.1872
        # Not all maxFragmentLen, specified by -M flag, is usable for the payload.  Based on current understanding of Iodine overhead (+3B) encoded + 12B non encoded:
        # Payload_size  = (hostname_len - 12 - 3 x (1 + 0.1872)) / (1 + 0.1872)
        ndp.maxFragmentLen = round((ndp.maxFragmentLen - 12 - 3 * (1 + codec_overhead)) / (1 + codec_overhead))
        # iodine downstream has a -m option
        # TODO Jiawei what is teh right value to put here?
        # Jiawei implemented on branch 48
        # Change eq maxFragmentLen = x . to eq maxUpFragmentLen = y .\n eq maxDownFragmentLen = z .
        #
        ndp.maxResponseLen = ymlconf.application.iodine.max_response_size
        # checked the patch is still applied to iodine src
        ndp.maxFragmentTx = 20
        pp = DNSProbabilisticParameters2()
        pp.ackTimeoutDelay = 1.0
        pp.initialPingDelay = 1.0
        out = Output()
        out.force_save = True
        out.preamble = [
            "set clear rules off .",
            "set print attribute off .",
            "set show advisories off ."
        ]
        return DNSHCSConfig2(name='corporate_iodine_mastodon',
                            topology=ymlconf.network,
                            output=out,
                            underlying_network=un,
                            weird_network=wn,
                            application=app,
                            background_traffic=bg,
                            nondeterministic_parameters=ndp,
                            probabilistic_parameters=pp)