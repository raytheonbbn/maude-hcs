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

from maude_hcs.lib.common.paramtopo import ParameterizedTopo
from maude_hcs.lib.dns.IodineDNSConfig import IodineDNSConfig
from Maude.attack_exploration.src.actors import Nameserver, Client
from Maude.attack_exploration.src.query import Query
from Maude.attack_exploration.src.network import *
from maude_hcs.lib.dns.iodineActors import TGenClient, Router, IodineClient, IodineServer, SendApp, ReceiveApp, WMonitor, PacedClient, IResolver
from maude_hcs.lib.dns.utils import makePackets
from maude_hcs.parsers.dnshcsconfig import DNSHCSConfig2
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
def corporate_iodine_mastodon(_args, hcsconf :  DNSHCSConfig2) -> IodineDNSConfig:
    def getOrAddTopologyNode(_name:str):
        node = hcsconf.topology.getNodebyLabel(_name)
        if node: return node
        node = Node.from_label(hcsconf.topology.nextID(), _name)
        hcsconf.topology.nodes.append(node)
        return node

    addr_prefix   = hcsconf.underlying_network.addr_prefix    
    root_node = getOrAddTopologyNode(hcsconf.underlying_network.root_name)
    assert root_node, "Root node undefined"
    tld_node = getOrAddTopologyNode(hcsconf.underlying_network.tld_name)
    assert tld_node, "TLD node undefined"
    ee_node = getOrAddTopologyNode(hcsconf.underlying_network.everythingelse_name)
    assert ee_node, "Everythingelse node undefined"
    # In this configuration, user alice contains the iodine client
    #   and user bob contains the iodine server
    # If these nodes dont exists, create them in the topology since
    # we assume that nodes correspond to actors (roughly)
    pwnd2_node = getOrAddTopologyNode(hcsconf.underlying_network.pwnd2_name)
    assert pwnd2_node, "PWND2 node undefined"
    corp_node = getOrAddTopologyNode(hcsconf.underlying_network.corporate_name)
    assert corp_node, "Corp node undefined"
    resolver_node = getOrAddTopologyNode(hcsconf.underlying_network.resolver_name)
    assert resolver_node, "Resolver node undefined"
    iodineCl_node = getOrAddTopologyNode(hcsconf.weird_network.client_name)
    assert iodineCl_node, "Iodine client node undefined"
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
    zoneCom, ns_records = createTLDZone(hcsconf, zoneRoot, record_ttl, inclPwnd=False)
    cacheRecords.extend(ns_records)
    # Auth zones
    zoneEverythingelse, ns_records = createAuthZone(hcsconf, ee_domain, ee_node.address, zoneCom, num_records, record_ttl, record_ttl_a, inclPwnd=True)
    cacheRecords.extend(ns_records)
    zonepwnd2, ns_records = createAuthZone(hcsconf, pwnd_domain, pwnd2_node.address, zoneCom, num_records, record_ttl, record_ttl_a)
    cacheRecords.extend(ns_records)
    zonecorp, ns_records = createAuthZone(hcsconf, corp_domain, corp_node.address, zoneCom, num_records, record_ttl, record_ttl_a)
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
    #nameserverPWND2 = Nameserver(pwnd2_node.address, [zonepwnd2])

    
    root_nameservers = {'a.root-servers.net.': root_node.address}

    # router
    router = Router(hcsconf.underlying_network.router)

    # tunnels     
    qtype = hcsconf.weird_network.client_weird_qtype
    iodineCl = IodineClient(iodineCl_node.address, pwnd_domain, qtype, nameserverCORP.address)
    iodineSvr = IodineServer(pwnd2_node.address, [zonepwnd2], hcsconf.weird_network.severWResponseTTL)
    monitorAddr = hcsconf.weird_network.monitor_address
    # applications
    aliceAddr = hcsconf.application.send_app_address
    bobAddr = hcsconf.application.rcv_app_address
    sndApp = SendApp(aliceAddr, bobAddr, hcsconf.application.sender_northbound_addr ,hcsconf.application.tunnel_client_addr)
    rcvApp = ReceiveApp(bobAddr, aliceAddr, hcsconf.application.receiver_northbound_addr, hcsconf.application.tunnel_server_addr)

    # monitor
    monitor = WMonitor(monitorAddr)
    clients = []

    # tgen client
    tgen_clients = []
    num_clients = hcsconf.background_traffic.num_clients
    for index,client in enumerate(hcsconf.background_traffic.clients):
        tgen_clients.append(TGenClient(f'tgen-dns-{index}', corp_node.address, 10000, client.client_retry_to, client.client_num_retry, client.client_markov_model_profile, client.start_time))
    C = IodineDNSConfig([router], monitor, [sndApp, rcvApp], [iodineCl, iodineSvr], clients, tgen_clients, [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP], root_nameservers, parameterized_network)
    C.set_params(hcsconf.nondeterministic_parameters.to_dict(), hcsconf.probabilistic_parameters.to_dict())
    C.set_preamble(hcsconf.output.preamble)
    C.set_model_type(_args.model)
    return C
