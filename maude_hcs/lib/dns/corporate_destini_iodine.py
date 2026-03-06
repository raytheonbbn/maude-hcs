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
    WMonitor, IResolver, DNSTGenClient, Ctr
from maude_hcs.parsers.masdnshcsconfig import MASHCSProtocolConfig, \
    MASBackgroundTrafficTgenClient, MASUnderlyingNetwork, MASWeirdNetwork
from .cache import CacheEntry, ResolverCache
from .corporate import createAuthZone, createRootZone, createTLDZone
import logging
import os

from .utils import extend_or_truncate
from .. import GLOBALS, Protocol
from ..common import X
from ..common.commonActors import ObservationPattern, AdversaryActor, generateBaselineBins, Msg
from ..mastodon.mastodonActors import MastodonServer, MastodonClient, MASTGenClient
from ..raceboat.raceboatActors import RaceboatClient, RaceboatServer, RbSendApp, RbRcvApp
from ...deps.dns_formalization.Maude.attack_exploration.src.zone import Record
from ...parsers.dnshcsconfig import DNSUnderlyingNetwork, DNSWeirdNetwork, DNSBackgroundTrafficTgenClient
from ...parsers.hcsconfig import HCSConfig
from ...parsers.markovJsonToMaudeParser import find_and_load_json
from ...parsers.quatexGenerator import QuatexGenerator
from ...parsers.ymlconf import Destini
from ...parsers.graph import Node, Link

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
    # did we override output directory?
    if _args.output_dir:
        hcsconf.output.directory = _args.output_dir
    # monitor address
    monitorAddr = hcsconf.monitor_address
    # These links contain link characteristics and have now the proper names.
    # This network get transformed later (see below)
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
    # adversary constants
    baselineBinSize = 1.0  # sec
    maxWindowSize = hcsconf.adversary.getMaxWindowSize('m')
    tlimit = 20 * maxWindowSize
    record_ttl    = underlying_network.record_ttl
    if tlimit > record_ttl:
        record_ttl = int(tlimit)
    record_ttl_a    = underlying_network.record_ttl_a
    # router
    router = Router(mas_underlying_network.router)

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
    nameserverCORP = Nameserver(corp_node.address, [zonecorp], forwardonly=X(resolver.address, True))
    #nameserverPWND2 = Nameserver(pwnd2_node.address, [zonepwnd2])
    root_nameservers = {'a.root-servers.net.': root_node.address}

    # tunnels (weird networks)
    weird_network = hcsconf.protocols[Protocol.IODINE_DNS.value].weird_network
    mas_weird_network = hcsconf.protocols[Protocol.DESTINI_MASTODON.value].weird_network
    # In this configuration, user alice contains the iodine client
    #   and user bob contains the iodine server
    # If these nodes dont exist, create them in the topology since we assume that nodes correspond to actors (roughly)
    # iodine tunnel
    iodineCl_node = getOrAddTopologyNode(weird_network.tunnel_client_addr)
    assert iodineCl_node, "Iodine client node undefined"
    iodineCl = IodineClient(iodineCl_node.address, pwnd_domain, weird_network.client_weird_qtype, nameserverCORP.address)
    iodineSvr = IodineServer(weird_network.tunnel_server_addr, [zonepwnd2], weird_network.severWResponseTTL)
    sndApp = SendApp(weird_network.send_app_address,
                     weird_network.rcv_app_address,
                     weird_network.tunnel_client_addr,
                     weird_network.sender_northbound_addr,
                     start=-1) # dont start it
    rcvApp = ReceiveApp(weird_network.rcv_app_address,
                        weird_network.send_app_address,
                        weird_network.tunnel_server_addr,
                        weird_network.receiver_northbound_addr,
                        start=-1) # dont start it

    ## raceboat tunnel client and server with
    rb_images = find_and_load_json(GLOBALS.TOPLEVELDIR, 'destini_covers.json')
    rb_destiniobj = Destini.from_dict(rb_images)
    raceboatCl = RaceboatClient(mas_weird_network.tunnel_client_addr, mas_weird_network.sender_northbound_addr,
                                mas_weird_network.alice_raceboat_profile,
                                rb_destiniobj, 'destini-covers', mastodon_server_address, True)
    raceboatSvr = RaceboatServer(mas_weird_network.tunnel_server_addr, mas_weird_network.receiver_northbound_addr,
                                mas_weird_network.bob_raceboat_profile, #'mas',
                                 rb_destiniobj, 'destini-covers',
                                mastodon_server_address, False)

    # adversary
    ## the smc measures
    maxNBinWindowSize = hcsconf.adversary.getMaxWindowSize('n')
    # the adversary is going to start at maxWindowSize because we will put the baseline data in the first window
    # we are also adding an offset to C.8 to count the number of tcp connections created by mastodon TGEN actors
    #   NOTE: this would not have mattered (noise) if hte thresholds weren't too small and sensitive to noise
    CONN_OFFSET = -1*len(hcsconf.protocols[Protocol.DESTINI_MASTODON.value].background_traffic.clients)
    adversary_conf = hcsconf.adversary.render_template(start_time=maxWindowSize, baseline_window=maxWindowSize, baseline_binsize=baselineBinSize,offset_baselines=True, other_offsets={'N_http_conn_post_nat' : CONN_OFFSET})
    # generate the adversaryX from template
    scenario_name = 'X'
    if _args.filename:
        scenario_name = f'_{_args.filename}'
    advFileName = f'adversary{scenario_name}.quatex'
    quatexGenerator = QuatexGenerator(template_path=os.path.join(hcsconf.output.smc_directory, 'adversary_param.j2'))
    quatexGenerator.generate_file(adversary_conf, os.path.join(hcsconf.output.smc_directory, advFileName))
    # generate the scalabilityX from template
    scalFileName = f'scalability{scenario_name}.quatex'
    quatexGenerator = QuatexGenerator(template_path=os.path.join(hcsconf.output.smc_directory, 'scalability_param.j2'))
    quatexGenerator.generate_file(adversary_conf, os.path.join(hcsconf.output.smc_directory, scalFileName))
    # generate the cp2 eval file
    quatexGenerator = QuatexGenerator(template_path=os.path.join(hcsconf.output.smc_directory, 'cp2_eval_param.j2'))
    quatexGenerator.generate_file({'adversary' : advFileName, 'scalability' : scalFileName},
                                  os.path.join(hcsconf.output.smc_directory, f'cp2_eval{scenario_name}.quatex'))

    ## the actor and observables
    def xformQuery(M, size):
        if size == 0: return M
        M1 = M.copy()
        M1.query.qname = extend_or_truncate(M.query.qname, size)
        return M1
    q = Query(0, f"www.{ee_domain}", 'A')
    msg = Msg(f'{resolver.address}', f'Z(0, {nameserverCORP.address})', q)
    baselineBinMsgs = generateBaselineBins(hcsconf.adversary.baseline_bins, 'dns_request', binSize=baselineBinSize, maxWindowSize=maxWindowSize, msg=msg, xform=xformQuery)
    """
        # these are offsets from start time for the differnet avg bin measures
        Extracts 'offset' values from sub-dictionaries in the input config
        and returns a new dictionary with keys formatted as '{original_key}_offset'.
        """
    offsets = {}
    for key, value in adversary_conf.items():
        # Check if the value is a dictionary and contains the 'offset' key
        if isinstance(value, dict) and 'offset' in value:
            offsets[f"{key}-offset"] = value['offset']
    adversary = AdversaryActor("adversary",
                          [ObservationPattern.ExtToLocalPreNat,
                            ObservationPattern.LocalToExtPostNat
                            ],
                          [ObservationPattern.ExtToLocalPostNat,
                           ObservationPattern.LocalToExtPreNat
                           ],
                           baselineBinMsgs,
                           offsets
                          )

    # applications
    app = hcsconf.protocols[Protocol.DESTINI_MASTODON.value].application
    mainSndApp = RbSendApp(app.alice_address, app.bob_address, sndApp.address, raceboatCl.userModelAddress, raceboatCl.contentManagerAddress, app.hashtags, app.xfiles, maxNBinWindowSize, maxWindowSize)
    mainRcvApp = RbRcvApp(app.bob_address, app.alice_address, rcvApp.address, raceboatSvr.userModelAddress,
                           raceboatSvr.contentManagerAddress, maxWindowSize)

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
        client.start_time = maxWindowSize # we are shifting the experiment in time to accommodate baseline data
        # TODO: undo the hardcoding of timeout back to client.client_retry_to
        tgen_clients.append(DNSTGenClient(f'tgen-dns-{index}', client.client_markov_model_profile, client.start_time, False, corp_node.address, 10000, 1.2, client.client_num_retry))
    for index, client in enumerate(hcsconf.protocols[Protocol.DESTINI_MASTODON.value].background_traffic.clients):
        assert isinstance(client, MASBackgroundTrafficTgenClient)
        client.start_time = maxWindowSize
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

    # transformation of the topology: we want links to/from router to be direct links instead
    #  Instead of mastodon clients to router, we will have
    #       mastodon clients to mastodon server as direct links
    #       this means that delays on client to router link are assumed to be zero and not to affect anything
    #       so delay/loss will be applied on messages as they egress clients
    # Similarly dns to router will be direct
    # create the links transforms dictionary
    topo_transforms = {}
    topo_transforms[Link(src_label=mastodon_server_address, dst_label=router.address)] = []
    topo_transforms[Link(dst_label=mastodon_server_address, src_label=router.address)] = []
    for client in tgen_clients:
        if isinstance(client, MASTGenClient):
            topo_transforms[Link(src_label=mastodon_server_address, dst_label=router.address)].append(Link(src_label=mastodon_server_address, dst_label=client.address_client))
            topo_transforms[Link(dst_label=mastodon_server_address, src_label=router.address)].append(Link(dst_label=mastodon_server_address, src_label=client.address_client))
    # add raceboat client mastodon client
    topo_transforms[Link(src_label=mastodon_server_address, dst_label=router.address)].append(
        Link(src_label=mastodon_server_address, dst_label=raceboatCl.masClientAddress))
    topo_transforms[Link(dst_label=mastodon_server_address, src_label=router.address)].append(
        Link(dst_label=mastodon_server_address, src_label=raceboatCl.masClientAddress))
    # add raceboat server mastodon client
    # topo_transforms[Link(src_label=mastodon_server_address, dst_label=router.address)].append(
    #     Link(src_label=mastodon_server_address, dst_label=raceboatSvr.masClientAddress))
    # topo_transforms[Link(dst_label=mastodon_server_address, src_label=router.address)].append(
    #     Link(dst_label=mastodon_server_address, src_label=raceboatSvr.masClientAddress))
    # DNS topo transforms
    topo_transforms[Link(src_label=resolver_node.label, dst_label=router.address)] = \
        [Link(src_label=resolver_node.label, dst_label=nameserverCORP.address)]
    topo_transforms[Link(dst_label=resolver_node.label, src_label=router.address)] = \
        [Link(dst_label=resolver_node.label, src_label=nameserverCORP.address)]
    # user bob communicates with mastodon server and resolver through its respective clients
    topo_transforms[Link(src_label=app.bob_address, dst_label=mastodon_server_address)] = \
        [Link(src_label=raceboatSvr.masClientAddress, dst_label=mastodon_server_address)]
    topo_transforms[Link(dst_label=app.bob_address, src_label=mastodon_server_address)] = \
        [Link(dst_label=raceboatSvr.masClientAddress, src_label=mastodon_server_address)]
    topo_transforms[Link(src_label=app.bob_address, dst_label=resolver_node.label)] = \
        [Link(src_label=iodineSvr.address, dst_label=resolver_node.label)]
    topo_transforms[Link(dst_label=app.bob_address, src_label=resolver_node.label)] = \
        [Link(dst_label=iodineSvr.address, src_label=resolver_node.label)]

    parameterized_network.transform(topo_transforms)

    # add some paramters
    pp = hcsconf.protocols[Protocol.IODINE_DNS.value].probabilistic_parameters
    pp.slimit = tlimit # is this good enough??
    if not pp.other:
        pp.other = {}
    # these are hacks for now (TODO put in the correct place)
    pp.other['encOH(fsize:Nat,ksize:Nat)'] = '(if ksize:Nat < fsize:Nat then 0 else ksize:Nat + (- fsize:Nat) fi)'
    pp.other['noiseMin(msg:Msg)'] = 0.001
    pp.other['exeDone(< mon:Address :  WMonitor | attrs:AttributeSet, doneFlag: true > conf:Config)'] = True
    pp.other['raceBoatMastodonClients'] = f'({raceboatCl.masClientAddress} ;; {raceboatSvr.masClientAddress})'
    # we are adding rules to
    pp.other['content-matches(C:Content)'] = 'isHttpReq(C:Content)'
    # query(0, 'mastodon . 'internet . 'com . root,a)
    mastodon_fqdn = hcsconf.protocols[Protocol.DESTINI_MASTODON.value].underlying_network.mastodon_fqdn
    dnsquery = Query(0, mastodon_fqdn, 'A')
    pp.other['add-to-sent(tm(tt:Float,to addr0:Address from addr1:Address : c:Content))'] = f'tm(tt:Float,to {resolver.address} from addr1:Address : {dnsquery.to_maude()})'

    C = IodineDNSConfig([Ctr(hcsconf.seed), router, adversary], monitor, [sndApp, rcvApp, mainSndApp, mainRcvApp], [iodineCl, iodineSvr, masServer, raceboatCl, raceboatSvr], clients, tgen_clients, [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP], root_nameservers, parameterized_network)
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
