import json
from pathlib import Path
from typing import List
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

from maude_hcs.parsers.shadowconf import parse_shadow_config
from .hcsconfig import Application, BackgroundTraffic, HCSConfig, NondeterministicParameters, Output, ProbabilisticParameters, UnderlyingNetwork, WeirdNetwork
from . import load_yaml_to_dict

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
class DNSBackgroundTraffic(BackgroundTraffic):
    """Dataclass for background traffic parameters."""    
    module: str = 'dns'
    num_paced_clients: int = 1
    paced_client_name: str = ''
    paced_client_Tlimit: int = 1
    paced_client_MaxQPS: int = 1

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
        bg.paced_client_Tlimit = 10 # ??
        bg.paced_client_MaxQPS = int(shadowconf.hosts['dnsperf'].getProcessByPName('./dnsperf_profiles.sh').args[-1])
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
        app_params = load_yaml_to_dict(file_path.parent.parent.parent.joinpath('application').joinpath(shadowconf.hosts['application_client'].getProcessByPName('python3').args[9]))
        assert shadowconf.hosts['application_client'].getProcessByPName('python3').args[10] == "-m", 'expected -m instead'
        mtu = int(shadowconf.hosts['application_client'].getProcessByPName('python3').args[11])
        ndp.packetSize = int((app_params['chunk_size_min']/100)*mtu)
        # > Read the pacing timeout values from `chunk_spacing_min` and `chunk_spacing_max` in the send application profile's yaml file.
        ndp.packetOverhead = 33
        ndp.maxMinimiseCount = 0
        # > Read the maximum fragment length from the maximum DNS request length limit (passed by the `-M` argument on the Iodine command line) and per-query overhead (currently unknown).
        assert shadowconf.hosts['application_client'].getProcessByPName('iodine').args[2] == "-M"
        ndp.maxFragmentLen = int(shadowconf.hosts['application_client'].getProcessByPName('iodine').args[3])
        ndp.maxFragmentTx = 20
        pp = DNSProbabilisticParameters()
        pp.maxPacketSize = int((app_params['chunk_size_max']/100)*mtu)
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