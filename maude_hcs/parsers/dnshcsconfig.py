import json
from typing import List
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

from .hcsconfig import Application, BackgroundTraffic, HCSConfig, NondeterministicParameters, ProbabilisticParameters, UnderlyingNetwork, WeirdNetwork


@dataclass_json
@dataclass
class DNSUnderlyingNetwork(UnderlyingNetwork):    
    root_name: str      = field(default="root")
    com_name:  str      = field(default="com")    
    populate_resolver_cache: bool   = field(default=True)
    record_ttl: int     = 3600
    addr_prefix: str    = 'addrNS'
    everythingelse_name: str    = ''
    everythingelse_num_records: int = 1
    pwnd2_name: str = ''
    pwnd2_base_name: str    =''
    resolver_name: str  =''
    corporate_name: str   ='' 

@dataclass_json
@dataclass
class DNSWeirdNetwork(WeirdNetwork):
    """Dataclass for the 'weird' (covert) network configuration."""
    client_address: str
    client_weird_qtype: str
    monitor_address: str      

@dataclass_json
@dataclass
class DNSNondeterministicParameters(NondeterministicParameters):
    """Dataclass for nondeterministic simulation parameters."""
    fileSize: int
    packetSize: int
    packetOverhead: int
    maxMinimiseCount: int
    maxFragmentLen: int
    maxFragmentTx: int

@dataclass_json
@dataclass
class DNSProbabilisticParameters(ProbabilisticParameters):
    """Dataclass for probabilistic simulation parameters."""
    maxPacketSize: int
    pacingTimeoutDelay: float
    pacingTimeoutDelayMax: float
    ackTimeoutDelay: float

@dataclass_json
@dataclass
class DNSBackgroundTraffic(BackgroundTraffic):
    """Dataclass for background traffic parameters."""    
    num_paced_clients: int
    paced_client_address_prefix: str
    paced_client_Tlimit: int
    paced_client_MaxQPS: int    

@dataclass_json
@dataclass
class SimplexApplication(Application):
    """Dataclass for the application layer configuration."""
    send_app_address: str
    overwrite_queue: bool
    send_app_queue_pkt_sizes: List[int]
    app_start_send_time: float
    rcv_app_address: str
    include_dns_client: bool

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
    def from_shadow(file_path: str) -> 'HCSConfig':
        pass
        # run_args = json.load(args.run_args)
        # run_args["shadow"] = {}
        # run_args["topology"] = {}
        # if args.shadow_filename:
        # sf = Path(args.shadow_filename)
        # shadow_conf  = parse_shadow_config(sf)
        # nf = sf.parent.joinpath(shadow_conf.network.graph_path)
        # topology_graph  = parse_shadow_gml(nf)
        # run_args["topology"] = {
        #     "node_names": get_node_names(topology_graph),
        #     "edges_delay": get_edge_delays_by_label(topology_graph),
        #     "edges_info": get_edge_info_by_label(topology_graph)
        # }

    #if _args.topology_filename:
    #   args          = run_args.get("topology")
    #   node_names    = args["node_names"]
    #   edges_info    = args["edges_info"]
    #   # Create a parameterized network object.  It needs more than edges_info.
    #   # edges_info is link characteristics from the shadow file.
    #   # We can hand these edges info to parameterized_network now because it already
    #   # has the proper names.  We will need to translate the other stuff.
    #   parameterized_network = ParameterizedNetwork(edges_info)
    #   # See if there exist shadow names; will be needed to grab link characteristics.
    #   EE_NAME       = find_node_name(node_names, [EE_NAME, "internet"])
    #   CORP_NAME     = find_node_name(node_names, [CORP_NAME, "local"])
    #   resolver_name = find_node_name(node_names, [resolver_name, "public"])
    #   PWND2_NAME    = find_node_name(node_names, [PWND2_NAME, "server"])
    #   iodineClAddr  = find_node_name(node_names, [CLIENT_NAME, "client"])
    #   ROOT_NAME     = find_node_name(node_names, ["root"], default="root")
    #   COM_NAME      = find_node_name(node_names, ["com", "tld"])
    #   # parameterized_network will attach the link characteristics, which have
    #   # shadow names, to the network defined in our config file, which has 
    #   # Maude_HCS names.
    #   # Translate the link names from Maude_HCS to shadow names to allow that
    #   # matching.
    #   links = ast.literal_eval(str(links)
    #                .replace("pwnd2_name", PWND2_NAME)
    #                .replace("client_address", iodineClAddr)
    #                .replace("resolver_name", resolver_name)
    #                .replace("corporate_name", CORP_NAME)
    #                .replace("everythingelse_name", EE_NAME)
    #                .replace("com", COM_NAME)
    #                # Assume root is not named explicitly in our use case.
    #                .replace("root", ROOT_NAME)
    #              )        