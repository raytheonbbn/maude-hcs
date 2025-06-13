# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# PWNDD Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# Contract No: HR00112590083
# Contractor Name: RTX BBN Technologies Inc.
# Contractor Address: 10 Moulton Street, Cambridge, Massachusetts 02138
#
# The U.S. Government's rights to use, modify, reproduce, release, perform,
# display, or disclose these technical data and software are defined in the
# Article VII: Data Rights clause of the OTA.
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
# contained herein.
#
# MAUDE_HCS: end

from maude_hcs.lib.dns.IodineDNSConfig import IodineDNSConfig
from Maude.attack_exploration.src.actors import Nameserver, Client
from Maude.attack_exploration.src.query import Query
from Maude.attack_exploration.src.network import *
from maude_hcs.lib.dns import DNS_GLOBALS
from maude_hcs.lib.dns.iodineActors import IodineClient, IodineServer, SendApp, ReceiveApp, WMonitor, PacedClient, IResolver
from maude_hcs.lib.dns.utils import makePackets
from .cache import CacheEntry, ResolverCache
from .corporate import createAuthZone, createRootZone, createTLDZone
import ast
from maude_hcs.parsers.graph import *
import logging

logger = logging.getLogger(__name__)

"""
    Parameters:
        _args is the command line args
        run_args is the json configuration from use cases
"""
def corporate_iodine(_args, run_args) -> IodineDNSConfig:
    preamble = run_args["output"].get("preamble", [])
    args = run_args["underlying_network"]
    addr_prefix = args.get("addr_prefix", "addrNS")

    # Get Maude_HCS names.
    EE_NAME       = args.get('everythingelse_name', 'example')
    PWND2_NAME    = args.get('pwnd2_name', 'pwnd2')
    CORP_NAME     = args.get('corporate_name', 'corp')
    resolver_name = args.get("resolver_name", "rAddr")
    num_records   = args.get('everythingelse_num_records', 1)
    populateCache = args.get('populate_resolver_cache', False)
    record_ttl = args.get('record_ttl', 3600)
    # Get links while we are at it.  For now, these have Maude_HCS names.
    links         = args.get("links")
    links.update(run_args["weird_network"].get("links"))
    CLIENT_NAME   = run_args["weird_network"]["client_address"]
    if _args.topology_filename:
      args          = run_args.get("topology")
      node_names    = args["node_names"]
      edges_info    = args["edges_info"]
      # Create a parameterized network object.  It needs more than edges_info.
      # edges_info is link characteristics from the shadow file.
      # We can hand these edges info to parameterized_network now because it already
      # has the proper names.  We will need to translate the other stuff.
      parameterized_network = ParameterizedNetwork(edges_info)
      # See if there exist shadow names; will be needed to grab link characteristics.
      EE_NAME       = find_node_name(node_names, [EE_NAME, "internet"])
      CORP_NAME     = find_node_name(node_names, [CORP_NAME, "local"])
      resolver_name = find_node_name(node_names, [resolver_name, "public"])
      PWND2_NAME    = find_node_name(node_names, [PWND2_NAME, "server"])
      iodineClAddr  = find_node_name(node_names, [CLIENT_NAME, "client"])
      ROOT_NAME     = find_node_name(node_names, ["root"], default="root")
      COM_NAME      = find_node_name(node_names, ["com", "tld"])
      # parameterized_network will attach the link characteristics, which have
      # shadow names, to the network defined in our config file, which has 
      # Maude_HCS names.
      # Translate the link names from Maude_HCS to shadow names to allow that
      # matching.
      links = ast.literal_eval(str(links)
                   .replace("pwnd2_name", PWND2_NAME)
                   .replace("client_address", iodineClAddr)
                   .replace("resolver_name", resolver_name)
                   .replace("corporate_name", CORP_NAME)
                   .replace("everythingelse_name", EE_NAME)
                   .replace("com", COM_NAME)
                   # Assume root is not named explicitly in our use case.
                   .replace("root", ROOT_NAME)
                 )
    else:
      ROOT_NAME             = "root"
      COM_NAME              = "com"
      # Need iodineClientAddr (required).
      iodineClAddr          = run_args["weird_network"]["client_address"]
      run_args.get("topology")["node_names"] = [EE_NAME, resolver_name, PWND2_NAME, iodineClAddr, CORP_NAME, ROOT_NAME, COM_NAME]
      # No shadow names, so translate the link names to Maude_HCS full names.
      links = ast.literal_eval(str(links)
                   .replace("pwnd2_name", PWND2_NAME)
                   .replace("client_address", iodineClAddr)
                   .replace("resolver_name", resolver_name)
                   .replace("corporate_name", CORP_NAME)
                   .replace("everythingelse_name", EE_NAME)
                   .replace("com", COM_NAME)
                   # Assume root is not named explicitly in our use case.
                   .replace("root", ROOT_NAME)
                 )
      # These links contain link characteristics and have now the proper names.
      parameterized_network = ParameterizedNetwork(links)

    ADDR_NS_ROOT  = f"{addr_prefix}{ROOT_NAME}"
    ADDR_NS_COM   = f"{addr_prefix}{COM_NAME}"

    
    cacheRecords = []
    # root zone

    zoneRoot, ns_records = createRootZone(run_args, record_ttl)
    cacheRecords.extend(ns_records)


    # com zone
    zoneCom, ns_records = createTLDZone(run_args, zoneRoot, record_ttl)
    cacheRecords.extend(ns_records)

    # EverythingElse EE zone

    zoneEverythingelse, ns_records = createAuthZone(EE_NAME,  f"{addr_prefix}{EE_NAME}", zoneCom, num_records, record_ttl)
    cacheRecords.extend(ns_records)
    # PWND2 domain name may be different than PWND2 server name.
    # TODO: Grab it from the shadow file, if available.
    pwd2_domain_name  = run_args["underlying_network"].get("pwnd2_base_name")
    zonepwnd2, ns_records = createAuthZone(pwd2_domain_name.rstrip(".com"), f"{addr_prefix}{PWND2_NAME}", zoneCom, num_records, record_ttl)  
    cacheRecords.extend(ns_records)
    zonecorp, ns_records = createAuthZone(CORP_NAME, f"{addr_prefix}{CORP_NAME}", zoneCom, num_records, record_ttl)
    cacheRecords.extend(ns_records)

    
    resolver = IResolver(resolver_name)
    cacheEntries = []
    for rec in cacheRecords:
        cacheEntries.append(CacheEntry(rec))
    # populate resolve cache with NS records and their corresponding A records?
    if populateCache:
        resolver.cache = ResolverCache('resolverCache', cacheEntries)


    nameserverRoot = Nameserver(ADDR_NS_ROOT, [zoneRoot])
    nameserverCom = Nameserver(ADDR_NS_COM, [zoneCom])
    nameserverEE = Nameserver(f'{addr_prefix}{EE_NAME}', [zoneEverythingelse])
    nameserverCORP = Nameserver(f'{addr_prefix}{CORP_NAME}', [zonecorp], forwardonly=resolver.address)
    nameserverPWND2 = Nameserver(f'{addr_prefix}{PWND2_NAME}', [zonepwnd2])

    
    root_nameservers = {'a.root-servers.net.': ADDR_NS_ROOT}

    # tunnels 
    args = run_args["weird_network"]
    iodineCl = IodineClient(iodineClAddr, pwd2_domain_name, args['client_weird_qtype'], nameserverCORP.address)
    iodineSvr = IodineServer(f'{addr_prefix}{PWND2_NAME}', nameserverPWND2)
    monitorAddr = args.get('monitor_address', DNS_GLOBALS.ADDR_MONITOR)
    # applications
    args = run_args["application"]
    pkt_sizes = args["send_app_queue_pkt_sizes"]
    overwrite_queue = args["overwrite_queue"]
    aliceAddr = args['send_app_address']
    bobAddr = args['rcv_app_address']    
    start_send_app = float(args["app_start_send_time"])
    include_dns_client = args['include_dns_client']
    args = args["background_traffic"]
    num_paced_clients = int(args['num_paced_clients'])
    paced_client_address = args['paced_client_address_prefix']
    paced_client_N = int(args['paced_client_Tlimit'] * args['paced_client_MaxQPS'])
    paced_client_TOP = 1.0 / args['paced_client_MaxQPS']
    paced_client_TOQ = 0.1 # not used 
    # app sends packets to the iodineClAddr
    packets = None if overwrite_queue else makePackets(aliceAddr, bobAddr, pkt_sizes)
    sndApp = SendApp(aliceAddr, bobAddr, iodineClAddr, packets, overwrite_queue, start_send_app)
    rcvApp = ReceiveApp(bobAddr)
    host_names = [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP, resolver, nameserverPWND2, iodineCl, iodineSvr]
    parameterized_network.create_links(host_names, links)
    
    # monitor
    monitor = WMonitor(monitorAddr)

    clients = []
    if include_dns_client:
        query = Query(1, f'www0.{EE_NAME}.com.', 'A')
        clients.append( Client('cAddr', [query], nameserverCORP) )

    # paced client
    paced_clients = []
    for i in range(num_paced_clients):        
        paced_clients.append(PacedClient(f'{paced_client_address}{i}', nameserverCORP.address, f'{EE_NAME}.com.', paced_client_N, paced_client_TOP, paced_client_TOQ))

    C = IodineDNSConfig(monitor, [sndApp, rcvApp], [iodineCl, iodineSvr], clients, paced_clients, [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP], root_nameservers, parameterized_network)
    C.set_params(run_args.get('nondeterministic_parameters', {}), run_args.get('probabilistic_parameters', {}))
    C.set_preamble(preamble)
    C.set_model_type(_args.model)
    return C
