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
from maude_hcs.lib.dns.iodineActors import TGenClient, Router, IodineClient, IodineServer, SendApp, ReceiveApp, \
    WMonitor, IResolver, DNSTGenClient
from maude_hcs.parsers.masdnshcsconfig import MASHCSProtocolConfig, \
    MASBackgroundTrafficTgenClient, MASUnderlyingNetwork, MASWeirdNetwork
from .cache import CacheEntry, ResolverCache
from .corporate import createAuthZone, createRootZone, createTLDZone
import logging

from .. import GLOBALS, Protocol
from ..mastodon.mastodonActors import MastodonServer, MastodonClient, MASTGenClient
from ...deps.dns_formalization.Maude.attack_exploration.src.zone import Record
from ...parsers.dnshcsconfig import DNSUnderlyingNetwork, DNSWeirdNetwork, DNSBackgroundTrafficTgenClient
from ...parsers.hcsconfig import HCSConfig
from ...parsers.markovJsonToMaudeParser import find_and_load_json
from ...parsers.ymlconf import Destini
from ...parsers.graph import Node

logger = logging.getLogger(__name__)

"""
    Parameters:
        _args is the command line args
        run_args is the json configuration from use cases
"""
def destini_mastodon_iodine_dns(_args, hcsconf :  HCSConfig) -> IodineDNSConfig:
    def getOrAddTopologyNode(_name:str):
        node = hcsconf.topology.getNodebyLabel(_name)
        if node: return node
        node = Node.from_label(hcsconf.topology.nextID(), _name)
        hcsconf.topology.nodes.append(node)
        return node

    monitorAddr = hcsconf.monitor_address

    # These links contain link characteristics and have now the proper names.
    parameterized_network = ParameterizedTopo(hcsconf.topology)

    # find the DNS underlying network conf
    assert Protocol.DESTINI_MASTODON.value in hcsconf.protocols, "Destini Mastodon underlying network undefined"
    assert Protocol.IODINE_DNS.value in hcsconf.protocols, "Iodine DNS underlying network undefined"
    underlying_network = hcsconf.protocols[Protocol.IODINE_DNS.value].underlying_network
    mas_underlying_network = hcsconf.protocols[Protocol.DESTINI_MASTODON.value].underlying_network
    addr_prefix   = underlying_network.addr_prefix
    root_node = getOrAddTopologyNode(underlying_network.root_name)
    assert root_node, "Root node undefined"
    tld_node = getOrAddTopologyNode(underlying_network.tld_name)
    assert tld_node, "TLD node undefined"
    ee_node = getOrAddTopologyNode(underlying_network.everythingelse_name)
    assert ee_node, "Everythingelse node undefined"
    pwnd2_node = getOrAddTopologyNode(underlying_network.pwnd2_name)
    assert pwnd2_node, "PWND2 node undefined"
    corp_node = getOrAddTopologyNode(underlying_network.corporate_name)
    assert corp_node, "Corp node undefined"
    resolver_node = getOrAddTopologyNode(underlying_network.resolver_name)
    assert resolver_node, "Resolver node undefined"
    tld_domain = underlying_network.tld_domain
    corp_domain = underlying_network.corporate_domain
    ee_domain = underlying_network.everythingelse_domain
    pwnd_domain = underlying_network.pwnd2_domain
    num_records   = underlying_network.everythingelse_num_records
    populateCache = underlying_network.populate_resolver_cache
    record_ttl    = underlying_network.record_ttl
    record_ttl_a    = underlying_network.record_ttl_a
    # router
    router = Router(underlying_network.router)

    # locate the mastodon underlying network
    # mastodon server
    mastodon_server_address = mas_underlying_network.mastodon_address
    masServer = MastodonServer(mastodon_server_address)
    
    cacheRecords = []
    # root zone
    zoneRoot, ns_records = createRootZone(hcsconf, Protocol.IODINE_DNS.value,  record_ttl)
    cacheRecords.extend(ns_records)
    # com zone
    zoneCom, ns_records = createTLDZone(hcsconf, Protocol.IODINE_DNS.value, zoneRoot, record_ttl, inclPwnd=False)
    cacheRecords.extend(ns_records)
    # Auth zones

    # the internet (auth) name server is authoritatie for zone pwnd.com and the A record for mastodon.pwnd.com
    mastodon_a_record = Record(hcsconf.protocols[Protocol.DESTINI_MASTODON.value].underlying_network.mastodon_fqdn, 'A', record_ttl_a, hcsconf.protocols[Protocol.DESTINI_MASTODON.value].underlying_network.mastodon_address)
    zoneEverythingelse, ns_records = createAuthZone(hcsconf, Protocol.IODINE_DNS.value, ee_domain, ee_node.address, zoneCom, num_records, record_ttl, record_ttl_a, True, [mastodon_a_record])
    cacheRecords.extend(ns_records)
    zonepwnd2, ns_records = createAuthZone(hcsconf, Protocol.IODINE_DNS.value, pwnd_domain, pwnd2_node.address, zoneCom, num_records, record_ttl, record_ttl_a)
    cacheRecords.extend(ns_records)
    zonecorp, ns_records = createAuthZone(hcsconf, Protocol.IODINE_DNS.value, corp_domain, corp_node.address, zoneCom, num_records, record_ttl, record_ttl_a)
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

    # tunnels (weird networks)
    weird_network = hcsconf.protocols[Protocol.IODINE_DNS.value].weird_network
    mas_weird_network = hcsconf.protocols[Protocol.DESTINI_MASTODON.value].weird_network
    # In this configuration, user alice contains the iodine client
    #   and user bob contains the iodine server
    # If these nodes dont exists, create them in the topology since we assume that nodes correspond to actors (roughly)
    # iodine tunnel
    iodineCl_node = getOrAddTopologyNode(weird_network.tunnel_client_addr)
    assert iodineCl_node, "Iodine client node undefined"
    iodineCl = IodineClient(iodineCl_node.address, pwnd_domain, weird_network.client_weird_qtype, nameserverCORP.address)
    iodineSvr = IodineServer(weird_network.tunnel_server_addr, [zonepwnd2], weird_network.severWResponseTTL)
    sndApp = SendApp(weird_network.send_app_address,
                     weird_network.rcv_app_address,
                     weird_network.sender_northbound_addr,
                     weird_network.tunnel_client_addr)
    rcvApp = ReceiveApp(weird_network.rcv_app_address,
                        weird_network.send_app_address,
                        weird_network.receiver_northbound_addr,
                        weird_network.tunnel_server_addr)

    ## raceboat tunnel client and server with
    rb_images = find_and_load_json(GLOBALS.TOPLEVELDIR, 'destini_covers.json')
    rb_destiniobj = Destini.from_dict(rb_images)


    # applications
    # TODO

    # monitor
    monitor = WMonitor(monitorAddr)
    clients = []

    def clean(s:str):
        return s.strip().replace('/', '').replace('\\','').replace('_', '-') # what else to clean here
    # tgen client
    tgen_clients = []
    seen_images = []
    for index,client in enumerate(hcsconf.protocols[Protocol.IODINE_DNS.value].background_traffic.clients):
        assert isinstance(client, DNSBackgroundTrafficTgenClient)
        tgen_clients.append(DNSTGenClient(f'tgen-dns-{index}', client.client_markov_model_profile, client.start_time, False, corp_node.address, 10000, client.client_retry_to, client.client_num_retry))
    for index, client in enumerate(hcsconf.protocols[Protocol.DESTINI_MASTODON.value].background_traffic.clients):
        assert isinstance(client, MASBackgroundTrafficTgenClient)
        # for now we are hardcoding images since neither the yml config nor the profile specify where these are
        #  mastodon_images.json was extracted using the `maude-hcs images` utility, see README
        # if tgens specify the same image dir we only gen image list once per unique dir (TODO test it)
        images_id = clean(client.clients_images_dir)
        destiniobj = None
        if images_id not in seen_images:
            seen_images.append(images_id)
            images = find_and_load_json(GLOBALS.TOPLEVELDIR, 'mastodon_images.json')
            destiniobj = Destini.from_dict(images)
        # output this once
        tgen_clients.append(MASTGenClient(f'tgen-mas-{index}', client.client_markov_model_profile, client.start_time, False, client.client_username, client.client_hashtags, destiniobj, images_id, mastodon_server_address, True))
    C = IodineDNSConfig([router], monitor, [sndApp, rcvApp], [iodineCl, iodineSvr, masServer], clients, tgen_clients, [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP], root_nameservers, parameterized_network)
    ndp = {}
    pp = {}
    for pname,protocol in hcsconf.protocols.items():
        if protocol.nondeterministic_parameters:
            ndp |= protocol.nondeterministic_parameters.to_dict()
        if protocol.probabilistic_parameters:
            pp |= protocol.probabilistic_parameters.to_dict()
    C.set_params(ndp, pp)
    C.set_preamble(hcsconf.output.preamble)
    C.set_model_type(_args.model)
    return C
