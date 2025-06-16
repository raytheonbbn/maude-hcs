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

from maude_hcs.lib.common.paramtopo import ParameterizedTopo
from maude_hcs.lib.dns.IodineDNSConfig import IodineDNSConfig
from Maude.attack_exploration.src.actors import Nameserver, Client
from Maude.attack_exploration.src.query import Query
from Maude.attack_exploration.src.network import *
from maude_hcs.lib.dns.iodineActors import IodineClient, IodineServer, SendApp, ReceiveApp, WMonitor, PacedClient, IResolver
from maude_hcs.lib.dns.utils import makePackets
from maude_hcs.parsers.dnshcsconfig import DNSHCSConfig
from .cache import CacheEntry, ResolverCache
from .corporate import createAuthZone, createRootZone, createTLDZone
from maude_hcs.parsers.graph import *
from maude_hcs.parsers.shadowconf import *
import logging

logger = logging.getLogger(__name__)

"""
    Parameters:
        _args is the command line args
        run_args is the json configuration from use cases
"""
def corporate_iodine(_args, hcsconf :  DNSHCSConfig) -> IodineDNSConfig:
    def getTopologyNode(_name:str):
        return hcsconf.topology.getNodebyLabel(_name)
    addr_prefix   = hcsconf.underlying_network.addr_prefix    
    root_node = getTopologyNode(hcsconf.underlying_network.root_name)
    assert root_node, "Root node undefined"
    tld_node = getTopologyNode(hcsconf.underlying_network.tld_name)
    assert tld_node, "TLD node undefined"
    ee_node = getTopologyNode(hcsconf.underlying_network.everythingelse_name)
    assert ee_node, "Everythingelse node undefined"
    pwnd2_node = getTopologyNode(hcsconf.underlying_network.pwnd2_name)
    assert pwnd2_node, "PWND2 node undefined"
    corp_node = getTopologyNode(hcsconf.underlying_network.corporate_name)
    assert corp_node, "Corp node undefined"
    resolver_node = getTopologyNode(hcsconf.underlying_network.resolver_name)
    assert resolver_node, "Resolver node undefined"
    iodineCl_node = getTopologyNode(hcsconf.weird_network.client_name)
    assert iodineCl_node, "Iodine client node undefined"
    bg_client_node = getTopologyNode(hcsconf.background_traffic.paced_client_name)
    assert bg_client_node, "Background traffic client undefined"
    tld_domain = hcsconf.underlying_network.tld_domain
    corp_domain = hcsconf.underlying_network.corporate_domain
    ee_domain = hcsconf.underlying_network.everythingelse_domain
    pwnd_domain = hcsconf.underlying_network.pwnd2_domain
    num_records   = hcsconf.underlying_network.everythingelse_num_records
    populateCache = hcsconf.underlying_network.populate_resolver_cache
    record_ttl    = hcsconf.underlying_network.record_ttl
    record_ttl_a    = hcsconf.underlying_network.record_ttl_a    
    
    # These links contain link characteristics and have now the proper names.
    parameterized_network = ParameterizedTopo(hcsconf.topology)
    
    cacheRecords = []
    # root zone
    zoneRoot, ns_records = createRootZone(hcsconf, record_ttl)
    cacheRecords.extend(ns_records)
    # com zone
    zoneCom, ns_records = createTLDZone(hcsconf, zoneRoot, record_ttl)
    cacheRecords.extend(ns_records)
    # Auth zones
    zoneEverythingelse, ns_records = createAuthZone(ee_domain, ee_node.address, zoneCom, num_records, record_ttl, record_ttl_a)
    cacheRecords.extend(ns_records)
    zonepwnd2, ns_records = createAuthZone(pwnd_domain, pwnd2_node.address, zoneCom, num_records, record_ttl, record_ttl_a)  
    cacheRecords.extend(ns_records)
    zonecorp, ns_records = createAuthZone(corp_domain, corp_node.address, zoneCom, num_records, record_ttl, record_ttl_a)
    cacheRecords.extend(ns_records)

    
    resolver = IResolver(resolver_node.address)
    cacheEntries = []
    for rec in cacheRecords:
        cacheEntries.append(CacheEntry(rec))
    # populate resolve cache with NS records and their corresponding A records?
    if populateCache:
        resolver.cache = ResolverCache('resolverCache', cacheEntries)


    nameserverRoot = Nameserver(root_node.address, [zoneRoot])
    nameserverCom = Nameserver(tld_node.address, [zoneCom])
    nameserverEE = Nameserver(ee_node.address, [zoneEverythingelse])
    nameserverCORP = Nameserver(corp_node.address, [zonecorp], forwardonly=resolver.address)
    nameserverPWND2 = Nameserver(pwnd2_node.address, [zonepwnd2])

    
    root_nameservers = {'a.root-servers.net.': root_node.address}

    # tunnels     
    qtype = hcsconf.weird_network.client_weird_qtype
    iodineCl = IodineClient(iodineCl_node.address, pwnd_domain, qtype, nameserverCORP.address)
    iodineSvr = IodineServer(pwnd2_node.address, nameserverPWND2, hcsconf.weird_network.severWResponseTTL)
    monitorAddr = hcsconf.weird_network.monitor_address
    # applications    
    pkt_sizes = hcsconf.application.send_app_queue_pkt_sizes
    overwrite_queue = hcsconf.application.overwrite_queue
    aliceAddr = hcsconf.application.send_app_address
    bobAddr = hcsconf.application.rcv_app_address
    start_send_app = float(hcsconf.application.app_start_send_time)
    include_dns_client = hcsconf.application.include_dns_client
    
    num_paced_clients = int(hcsconf.background_traffic.num_paced_clients)    
    paced_client_N = int(hcsconf.background_traffic.paced_client_Tlimit * hcsconf.background_traffic.paced_client_MaxQPS)
    paced_client_TOP = 1.0 / hcsconf.background_traffic.paced_client_MaxQPS
    paced_client_TOQ = 0.1 # not used 
    # app sends packets to the iodineClAddr
    packets = None if overwrite_queue else makePackets(aliceAddr, bobAddr, pkt_sizes)
    sndApp = SendApp(aliceAddr, bobAddr, iodineCl_node.address, packets, overwrite_queue, start_send_app)
    rcvApp = ReceiveApp(bobAddr)

    # monitor
    monitor = WMonitor(monitorAddr)
    clients = []
    if include_dns_client:
        query = Query(1, f'www.{ee_domain}', 'A')
        clients.append( Client('cAddr', [query], nameserverCORP) )

    # paced client
    paced_clients = []
    client_suffixes = ['']
    if num_paced_clients > 1:
        client_suffixes = range(num_paced_clients)
    for suffix in client_suffixes:
        paced_clients.append(PacedClient(f'{bg_client_node.address}{suffix}', nameserverCORP.address, ee_domain, paced_client_N, paced_client_TOP, paced_client_TOQ))
    C = IodineDNSConfig(monitor, [sndApp, rcvApp], [iodineCl, iodineSvr], clients, paced_clients, [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP], root_nameservers, parameterized_network)    
    C.set_params(hcsconf.nondeterministic_parameters.to_dict(), hcsconf.probabilistic_parameters.to_dict())
    C.set_preamble(hcsconf.output.preamble)
    C.set_model_type(_args.model)
    return C
