from maude_hcs.lib.dns.IodineDNSConfig import IodineDNSConfig
from Maude.attack_exploration.src.actors import Resolver, Nameserver, Client
from Maude.attack_exploration.src.query import Query
from Maude.attack_exploration.src.network import ParameterizedNetwork
from maude_hcs.lib.dns import DNS_GLOBALS
from maude_hcs.lib.dns.iodineActors import IodineClient, IodineServer, SendApp, ReceiveApp, WMonitor
from maude_hcs.lib.dns.utils import makePackets
from .corporate import createAuthZone, createRootZone, createTLDZone
import ast
from maude_hcs.parsers.graph import *
import logging

logger = logging.getLogger(__name__)

def corporate_iodine(_args, run_args) -> IodineDNSConfig:
    args = run_args["underlying_network"]
    addr_prefix = args.get("addr_prefix", "addrNS")
    #EE_NAME = args.get('everythingelse_name', 'everythingelse')
    #PWND2_NAME = args.get('pwnd2_name', 'pwnd2')
    #CORP_NAME = args.get('corporate_name', 'corp')
    num_records = args.get('everythingelse_num_records', 1)
    #resolver_name = args.get("resolver_name", "rAddr")
    links_args  = args.get("links")
    args          = run_args.get("topology")
    node_names    = args.get("node_names")
    edges_info    = args.get("edges_info")
    # Use the shadow file names and addresses into our assumed topology.  This 
    # ends up being a sort of mapping between names.
    EE_NAME       = find_node_name(node_names, ["everythingelse", "internet"])
    CORP_NAME     = find_node_name(node_names, ["corp", "local"])
    resolver_name = find_node_name(node_names, ["rAddr", "public"])
    PWND2_NAME    = find_node_name(node_names, ["pwnd2", "tld"])
    iodineClAddr  = find_node_name(node_names, ["iodineC", "client"])
    ROOT_NAME     = find_node_name(node_names, ["root"])
    COM_NAME      = find_node_name(node_names, ["com", "internet"])
    ADDR_NS_ROOT  = f"{addr_prefix}{ROOT_NAME}"
    ADDR_NS_COM   = f"{addr_prefix}{COM_NAME}"
    
    # root zone
    zoneRoot = createRootZone(args)

    # com zone
    zoneCom = createTLDZone(run_args, zoneRoot)

    # EverythingElse EE zone
    zoneEverythingelse = createAuthZone(EE_NAME, zoneCom, num_records)
    zonepwnd2 = createAuthZone(PWND2_NAME, zoneCom, num_records)  
    zonecorp = createAuthZone(CORP_NAME, zoneCom, num_records)
    
    resolver = Resolver(resolver_name) 

    nameserverRoot = Nameserver(ADDR_NS_ROOT, [zoneRoot])
    nameserverCom = Nameserver(ADDR_NS_COM, [zoneCom])
    nameserverEE = Nameserver(f'{addr_prefix}{EE_NAME}', [zoneEverythingelse])
    nameserverCORP = Nameserver(f'{addr_prefix}{CORP_NAME}', [zonecorp], forwardonly=resolver.address)
    nameserverPWND2 = Nameserver(f'{addr_prefix}{PWND2_NAME}', [zonepwnd2])

    
    root_nameservers = {'a.root-servers.net.': ADDR_NS_ROOT}

    # tunnels 
    args = run_args["weird_network"]
    #iodineClAddr = args['client_address']
    iodineCl = IodineClient(iodineClAddr, args['client_weird_base_name'], args['client_weird_qtype'], nameserverCORP.address)
    iodineSvr = IodineServer(f'{addr_prefix}{PWND2_NAME}', nameserverPWND2)
    links_args.update(args["links"])
    monitorAddr = args.get('monitor_address', DNS_GLOBALS.ADDR_MONITOR)
    # applications
    args = run_args["application"]
    pkt_sizes = args["send_app_queue_pkt_sizes"]
    aliceAddr = args['send_app_address']
    bobAddr = args['rcv_app_address']    
    start_send_app = float(args["app_start_send_time"])
    include_dns_client = args['include_dns_client']
    # app sends packets to the iodineClAddr
    sndApp = SendApp(aliceAddr, iodineClAddr, makePackets(aliceAddr, bobAddr, pkt_sizes), start_send_app)
    rcvApp = ReceiveApp(bobAddr)
    # Links:
    link_characteristics = run_args["link_characteristics"]
    print(f"Topo info: {get_edge_delays_by_label(parse_shadow_gml(_args.topology_filename))}")
    # Replace the actor names to the links.
    links_args  = ast.literal_eval(str(links_args)
                    .replace("pwnd2_name", PWND2_NAME)
                    .replace("client_address", iodineClAddr)
                    .replace("resolver_name", resolver_name)
                    .replace("corporate_name", CORP_NAME)
                    .replace("everythingelse_name", EE_NAME)
                    )
    parameterized_network = ParameterizedNetwork([nameserverRoot, nameserverCom, nameserverEE, nameserverCORP, resolver, nameserverPWND2, iodineCl, iodineSvr],
                                                 edges_info)
    
    # monitor
    monitor = WMonitor(monitorAddr)
    
    clients = []
    if include_dns_client:
        query = Query(1, f'www0.{EE_NAME}.com.', 'A')
        clients.append( Client('cAddr', [query], nameserverCORP) )

    C = IodineDNSConfig(monitor, [sndApp, rcvApp], [iodineCl, iodineSvr], clients, [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP], root_nameservers, parameterized_network)
    C.set_params(run_args.get('nondeterministic_parameters', {}), run_args.get('probabilistic_parameters', {}))
    C.set_model_type(_args.model)
    return C

