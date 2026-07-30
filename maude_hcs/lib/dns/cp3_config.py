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

import os
import traceback
import logging

from pathlib import Path
from maude_hcs.lib import GLOBALS, flatten
from .cache import ResolverCache
from Maude.attack_exploration.src.conversion_utils import address_to_maude, name_to_maude

from maude_hcs.lib.common.paramtopo import ParameterizedTopo
from Maude.attack_exploration.src.actors import Nameserver
from Maude.attack_exploration.src.query import Query
from Maude.attack_exploration.src.network import *
from maude_hcs.lib.dns.iodineActors import TGenClient, Router, IodineClient, IodineServer, SendApp, ReceiveApp, \
    WMonitor, IResolver, DNSTGenClient, Ctr
from maude_hcs.parsers.masdnshcsconfig import MASBackgroundTrafficTgenClient
from .cache import CacheEntry, ResolverCache
from .corporate import createAuthZone, createRootZone, createTLDZone

from .utils import extend_or_truncate
from .. import GLOBALS, Protocol
from ..common import X
from ..common.actor import AdversaryActor
from ..mastodon.mastodonActors import MastodonServer, MASTGenClient
from ..raceboat.raceboatActors import RaceboatClient, RaceboatServer, RbSendApp, RbRcvApp
from ...deps.dns_formalization.Maude.attack_exploration.src.zone import Record
from ...parsers.dnshcsconfig import DNSBackgroundTrafficTgenClient
from ...parsers.hcsconfig import HCSConfig
from ...parsers.markovJsonToMaudeParser import find_and_load_json
from ...parsers.quatexGenerator import QuatexGenerator
from ...parsers.ymlconf import Destini
from ...parsers.graph import Node, Link
from ...parsers.markovJsonToMaudeParser import find_recursively
from ..common import get_relative_file_path

TOPLEVELDIR = Path(os.path.dirname(__file__)).parent.parent
DNS_MAUDE_ROOT = Path("deps/dns_formalization/Maude")
WEIRD_DNS_MAUDE_ROOT = Path(os.path.dirname(__file__)).joinpath(Path("maude/"))

CWD = Path.cwd()

class CP3Config:
    
    def __init__(self, standaloneActors, monitor, applications, weird_networks, clients, paced_clients, resolvers, nameservers, root_nameservers, network, output_dir) -> None:

        self.standaloneActors = standaloneActors
        self.monitor = monitor
        self.paced_clients = paced_clients
        print(clients)
        self.applications = applications
        self.tunnels = weird_networks
        self.output_dir = output_dir

        self.path = str(TOPLEVELDIR.joinpath(DNS_MAUDE_ROOT)) + os.path.sep
        self.weirdpath = str(WEIRD_DNS_MAUDE_ROOT)
        self.preamble = None

        self.clients = clients
        self.resolvers = resolvers
        self.nameservers = nameservers

        self.root_nameservers = root_nameservers
        self.network  = network

        self.monitor_address = 'mAddr'

        self.common_path = Path(self.weirdpath).parent.parent.joinpath('common').joinpath('maude')

    def _get_actor_addresses(self):
        addresses = [self.monitor_address]
        for client in self.clients:
            addresses.append(client.address)
        for resolver in self.resolvers:
            addresses.append(resolver.address)
        for nameserver in self.nameservers:
            addresses.append(nameserver.address)

        for router in self.standaloneActors:
            if router.address:
                addresses.append(router.address)
        for client in self.paced_clients:
            addresses.append(client.address)
            if isinstance(client, TGenClient):
                addresses += client.getAddresses()
        for app in self.applications:
            addresses.append(app.address)
        for actor in self.tunnels:
            addresses.append(actor.address)
            if isinstance(actor, RaceboatClient) or isinstance(actor, RaceboatServer):
                addresses.append(actor.userModelAddress)
                addresses.append(actor.contentManagerAddress)
                addresses.append(actor.destiniAddress)
                addresses.append(actor.masClientAddress)
        return sorted(set(addresses))

    def _get_addr_ops(self) -> str:
        res = '--- Actor addresses\n'
        res += f'ops ' + ' '.join(self._get_actor_addresses()) + ' : -> Address .\n'
        return res

    def _get_sbelt(self) -> str:
        res = '--- "SBELT": fallback if there are no known name servers\n'
        res += 'op sb : -> ZoneState .\n'
        
        res += 'eq sb = < root ('
        res += ', '.join(f'{name_to_maude(name)} |-> {self.root_nameservers[name]}' \
            for name in self.root_nameservers)
        res += ') > .\n'

        return res
    
    def _get_zones(self):        
        """
        Also include zones from any weird name servers
        return set([zone for zonelist in map(lambda ns: ns.zones, self.nameservers) for zone in zonelist])
        """       
        zones = set([zone for zonelist in map(lambda ns: ns.zones, self.nameservers) for zone in zonelist]) 
        for actor in self.tunnels:
            if isinstance(actor, IodineServer):
                zones = zones.union(set(actor.zones))
        return zones

    def _to_maude_common_definitions(self, param_dict) -> str:
        defs = 'eq monitorQueryLog? = true .\n\n'

        for param, val in param_dict.items():
            if isinstance(val, str):
                defs += f'eq {param} = {val} .\n'
            else:
                defs += f'eq {param} = {str(val).lower()} .\n'

        defs += '\n'

        defs += self._get_addr_ops() + '\n'
        defs += self._get_sbelt() + '\n'
        defs += self._to_maude_zones()

        # Tgen actors and raceboat/destini have image list defs, include here
        new_defs = set()
        for client in sorted(self.paced_clients, key=lambda x: x.address):
            if isinstance(client, MASTGenClient):
                _d = client.to_maude_defs()
                if _d.strip():
                    new_defs.add(_d)
        for tun in sorted(self.tunnels, key=lambda x: x.address):
            if isinstance(tun, RaceboatClient):
                _d = tun.to_maude_defs()
                if _d.strip():
                    new_defs.add(_d)
        for app in sorted(self.applications, key=lambda x: x.address):
            if isinstance(app, RbSendApp):
                _d = app.to_maude_defs()
                if _d.strip():
                    new_defs.add(_d)
        for actr in self.standaloneActors:
            if isinstance(actr, AdversaryActor):
                _d = actr.to_maude_defs()
                if _d.strip():
                    new_defs.add(_d)
        defs += '\n'.join(sorted(new_defs))
        defs += '\n'
        return defs

    def to_relative_path(self, path):
        return get_relative_file_path(self.output_dir, path)

    def _to_maude_zones(self) -> str:
        res = '--- Zone files\n'
        for zone in self._get_zones():
            res += zone.to_maude() + '\n\n'
        return res

    # Override
    def _maude_loads(self, path, model) -> str:
        # sload ../../../mastodon/maude/probabilistic/mastodon
        # sload ../../../app/maude/probabilistic

        res = '--- This maude file has been created automatically from the Python representation ---\n'
        res += '\n'.join([
            f'sload {self.to_relative_path(self.weirdpath + "/probabilistic/iodine_dns")}',
            f'sload {self.to_relative_path(Path(self.weirdpath).parent.parent.joinpath('tgen').joinpath('maude').joinpath('dnsTgen-actor-uniqueId'))}\n'                
            f'sload {self.to_relative_path(self.common_path.joinpath("user-action-actor"))}\n'
            f'sload {self.to_relative_path(Path(self.weirdpath).parent.parent.joinpath('tgen').joinpath('maude').joinpath('masTGen.maude'))}\n'
            f'sload {self.to_relative_path(Path(self.weirdpath).parent.parent.joinpath('mastodon').joinpath('maude').joinpath('probabilistic').joinpath('mastodon'))}',
            f'sload {self.to_relative_path(Path(self.weirdpath).parent.parent.joinpath('app').joinpath('maude').joinpath('probabilistic-no-rb'))}',
            f'sload {self.to_relative_path(Path(self.weirdpath).parent.parent.joinpath('raceboat').joinpath('rb-cm-client-hash'))}',
            f'sload {self.to_relative_path(Path(self.weirdpath).parent.parent.joinpath('raceboat').joinpath('rb-cm-server'))}',
            f'sload {self.to_relative_path(Path(self.weirdpath).parent.parent.joinpath('raceboat').joinpath('enc-dec-actor'))}',
            f'sload {self.to_relative_path(Path(self.weirdpath).parent.parent.joinpath('common').joinpath('maude').joinpath('http-overhead'))}',
            f'sload {self.to_relative_path(self.common_path.joinpath("router"))}',
            f'sload {self.to_relative_path(self.common_path.joinpath("adversary-observer"))}'
        ])
        tgen_loads = set()
        for tc in self.paced_clients:
            if isinstance(tc, TGenClient):
                # we change the mmodel file when we create the maude name so change it back
                mod = '_'.join(tc.profile.replace('-', '_').split('_')[1:])
                key = None # since dns and mastodon profiles can use same names, key is used to distinguish
                if isinstance(tc, MASTGenClient):
                    key = 'mastodonprofiles'
                elif isinstance(tc, DNSTGenClient):
                    key = 'dnsprofiles'
                file = find_recursively(GLOBALS.TOPLEVELDIR, f'config_{mod}.maude', key=key)
                tgen_loads.add(f'sload {self.to_relative_path(file)}')
        rb_loads = set()
        for actor in self.tunnels:
            if isinstance(actor, RaceboatClient) or isinstance(actor, RaceboatServer):
                mod = '_'.join(actor.profile.replace('-', '_').split('_')[1:])
                try:
                    file = find_recursively(GLOBALS.TOPLEVELDIR, f'{mod}.maude')
                    rb_loads.add(f'sload {self.to_relative_path(file)}')
                except:
                    logger.warning(f'Could not find {mod}.maude. Exception {traceback.format_exc()}')

        if tgen_loads:
            res += '\n ---- tgen models\n'
            res += '\n'.join(sorted(tgen_loads))
        if rb_loads:
            res += '\n ---- raceboat models\n'
            res += '\n'.join(sorted(rb_loads))

        return res

    # override
    def _maude_includes(self, params, path, model):
        #           'inc MASTODON .',
        #           'inc MAS-TGEN .',
        #           'inc CP2_APP .',

        includes = [
            ' inc DNS .',
            ' inc USER-ACTION-ACTOR .',
            ' inc DNS-TGEN .',
            ' inc IODINE_DNS . --- + TEST-HELPERS .',
            ' inc ROUTER .',
            ' inc MASTODON .',
            ' inc MAS-TGEN .',
            ' inc ADVERSARY-OBSERVER .',
            ' inc CP2_APP .',
            'inc ENC-DEC .',
            'inc CONTENT-MANAGER-CLIENT .',
            'inc CONTENT-MANAGER-SERVER .',
            'inc HTTP-OVERHEAD .'
        ]

        res = '\n'.join(includes)
        # TGEN models
        tgen_incs = set()
        for tc in self.paced_clients:
            if isinstance(tc, TGenClient):
                tgen_incs.add(f' inc {tc.profile.upper()}-MAMODEL .')
        if tgen_incs:
            res += '\n ---- tgen model includes\n'
            res += '\n'.join(sorted(tgen_incs))
            # res += '\n'
        # Raceboat models
        rb_incs = set()
        for actor in self.tunnels:
            if isinstance(actor, RaceboatClient) or isinstance(actor, RaceboatServer):
                rb_incs.add(f' inc {actor.profile.upper()}-MAMODEL .')
        if rb_incs:
            res += '\n ---- raceboat model includes\n'
            res += '\n'.join(sorted(rb_incs))
            res += '\n'
        return res

    # Override to add tunnels and applications to conf
    def _to_maude_actors(self) -> str:
        res = '  --- Clients\n'
        for client in self.clients:
            res += '  ' + client.to_maude() + '\n'

        res += '  --- Resolvers\n'
        for resolver in self.resolvers:
            res += '  ' + resolver.to_maude() + '\n'

        res += '  --- Nameservers\n'
        for nameserver in self.nameservers:
            res += '  ' + nameserver.to_maude() + '\n'

        res += '  --- standalone actors\n'
        for router in self.standaloneActors:
            res += '  ' + router.to_maude() + '\n'
        res += '  --- tunnels\n'
        for tunnel in self.tunnels:
            res += '  ' + tunnel.to_maude() + '\n'
        
        res += '  --- applications\n'
        for application in self.applications:
            res += '  ' + application.to_maude() + '\n'
        
        # add the start messages if requested
        # include the monitor for the quantitative analysis        
        res += '  --- WMonitor\n'
        res += '  ' + self.monitor.to_maude() + '\n'
        res += '  --- tgens \n'
        for client in self.paced_clients:
            res += '  ' + client.to_maude() + '\n'
            if client.start:
                res += f'  [genRandom(0.0, 0.0001), to {address_to_maude(client.address)} : start, 0]\n'
        res += '  --- App start messages\n'
        for app in self.applications:
            if isinstance(app, SendApp) and app.start >= 0:
                res += f'  [{str(app.start)}, (to {address_to_maude(app.address)} : start), 0] \n'
            if isinstance(app, ReceiveApp) and app.start >= 0: # TODO: testing for Bob also add start messages for RecvApp
                res += f'  [1.0, (to {address_to_maude(app.address)} : start), 0] \n'
        
        return res

    def set_params(self, nondet_params : dict, prob_params : dict):
        self.nondet_params = nondet_params
        self.prob_params = prob_params
    
    def set_model_type(self, type):
        if not type in GLOBALS.MODEL_TYPES:
            raise Exception(f'Type {type} must be in {GLOBALS.MODEL_TYPES}')
        self.model_type = type

    def set_preamble(self, L: list[str] = []):
        self.preamble = L
    
    def _to_maude_caches(self) -> str:
        res = '--- Caches\n'
        for resolver in self.resolvers:
            if resolver.cache:
                res += resolver.cache.to_maude() + '\n'
        return res

    def _to_maude_address_defs(self) -> str:
        res = ""
        addrs = self._get_actor_addresses()
        for addr in addrs:
            res += f"eq {addr} = a(srvN[1],hcs,wt,srv,1) .\n"
        return res

    def to_maude_prob(self, param_dict, path) -> str:
        # preamble
        res = '\n'.join([pr for pr in self.preamble])
        res += '\n\n'

        # sloads
        res += self._maude_loads(path, 'prob')
        res += '\n\n'

        # start defining module
        res += f'mod {GLOBALS.MODULE_NAME} is\n'

        # define includes
        res += self._maude_includes(param_dict, path, 'prob')

        # parameters
        res += self._to_maude_common_definitions(flatten(param_dict))
        res += '\n'

        # caches
        res += self._to_maude_caches()
        res += '\n'

        res += self._to_maude_address_defs()
        res += '\n'
        
        res += '--- Initial configuration\n'
        res += 'op initState : -> Config .\n'
        res += 'eq initState =\n'
        res += '  --- Client start messages\n'
        for client in self.clients:
            res += f'  [id, (to {client.address} : start), 0]\n'
        res += self._to_maude_actors()
        res += '  .\n\n'
        
        res += self.network.to_maude_network()
        res += '\n'
        res += 'op initConfig : -> Config .\n'
        res += 'eq initConfig = run({0.0 | nil} initState,slimit) .\n'
        res += 'endm\n'

        return res       

    def to_maude(self):
        params = self.nondet_params.copy()
        params.update(self.prob_params)
        return self.to_maude_prob(params, self.path)





















def mk_cp3_config(hcsconf: HCSConfig) -> CP3Config:
    def getOrAddTopologyNode(_name:str):
        node = hcsconf.topology.getNodebyLabel(_name)
        if node: return node
        node = Node.from_label(hcsconf.topology.nextID(), _name)
        hcsconf.topology.nodes.append(node)
        return node
    
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
    maxWindowSize = 5 #TODO FIX THIS ignoring adversary for now, using mock values hcsconf.adversary.getMaxWindowSize('m')
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
    maxNBinWindowSize = 5 #TODO FIX THIS ignoring adversary for now, using mock values hcsconf.adversary.getMaxWindowSize('n')
    # the adversary is going to start at maxWindowSize because we will put the baseline data in the first window
    # we are also adding an offset to C.8 to count the number of tcp connections created by mastodon TGEN actors
    #   NOTE: this would not have mattered (noise) if hte thresholds weren't too small and sensitive to noise
    CONN_OFFSET = -1*len(hcsconf.protocols[Protocol.DESTINI_MASTODON.value].background_traffic.clients)
    # It seems there is a constant number of pre nat connection from Alice at the beginning that we arent count
    # so we offset by this constant TODO: undersntad where this is coming from
    CONN_OFFSET_PRENAT = -1*8
    # DNS query offset: our models do not send a DNS query every time we send an HTTP request;
    # instead we use the add-to-sent below to inject a DNS query for each HTTP request
    # we constrain this injection to only HTTP requests from Alice because alice creates a new connection per request
    #   whereas the mastodon tgen clients reuse a connection (so they resolve the domain name once);
    #   This however requires adding #tgens DNS resolutions, one per which is is the purpose of this DNS count offset
    DNS_CNT_OFFSET = CONN_OFFSET

    ## the actor and observables
    def xformQuery(M, size):
        if size == 0: return M
        M1 = M.copy()
        M1.content.qname = extend_or_truncate(M.content.qname, size)
        return M1

    def xformHttpRequest(M, size):
        if size == 0: return M
        M1 = M.copy()
        M1.content.lenBytes = size
        return M1

    def identity(M, size):
        return M
    

    '''
    Requires adversary defined

    q = Query(0, f"www.{ee_domain}", 'A')
    msg = Msg(f'{resolver.address}', f'Z(0, {nameserverCORP.address})', q)
    dnsReqBaselineBinMsgs = generateBaselineBins(hcsconf.adversary.baseline_bins, 'dns_request',
                                                 binSize=baselineBinSize, maxWindowSize=maxWindowSize, msg=msg,
                                                 xform=xformQuery)
    httpReq = HttpRequestPost("baseline.jpg", 0)
    msg = Msg(f'{mastodon_server_address}', f'Z(0, tgen-mas-0)', httpReq)
    httpUpstreamBytesBinMsgs = generateBaselineBins(hcsconf.adversary.baseline_bins, 'http_upstream_bytes',
                                                    binSize=baselineBinSize, maxWindowSize=maxWindowSize, msg=msg,
                                                    xform=xformHttpRequest)
    # get the total bytes we need these to offset threshold by
    TOTAL_HTTP_BYTES_OFFSET = sum([m.msg.content.lenBytes for m in httpUpstreamBytesBinMsgs.msgs])
    baselineMsgs = dnsReqBaselineBinMsgs.merge(httpUpstreamBytesBinMsgs)

    adversary_conf = hcsconf.adversary.render_template(
        start_time=maxWindowSize,
        baseline_window=maxWindowSize,
        baseline_binsize=baselineBinSize,
        offset_baselines=True,
        other_offsets={
            'N_http_conn_post_nat' : CONN_OFFSET,
            'N_http_conn_pre_nat' : CONN_OFFSET_PRENAT,
            'N_query_post_nat' : DNS_CNT_OFFSET,
            'N_http_upload_post_nat' : TOTAL_HTTP_BYTES_OFFSET
        }
    )


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
                           baselineMsgs,
                           offsets
                          )
    '''


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
    topo_transforms[Link(src_label=resolver_node.name, dst_label=router.address)] = \
        [Link(src_label=resolver_node.name, dst_label=nameserverCORP.address)]
    topo_transforms[Link(dst_label=resolver_node.name, src_label=router.address)] = \
        [Link(dst_label=resolver_node.name, src_label=nameserverCORP.address)]
    # user bob communicates with mastodon server and resolver through its respective clients
    topo_transforms[Link(src_label=app.bob_address, dst_label=mastodon_server_address)] = \
        [Link(src_label=raceboatSvr.masClientAddress, dst_label=mastodon_server_address)]
    topo_transforms[Link(dst_label=app.bob_address, src_label=mastodon_server_address)] = \
        [Link(dst_label=raceboatSvr.masClientAddress, src_label=mastodon_server_address)]
    topo_transforms[Link(src_label=app.bob_address, dst_label=resolver_node.name)] = \
        [Link(src_label=iodineSvr.address, dst_label=resolver_node.name)]
    topo_transforms[Link(dst_label=app.bob_address, src_label=resolver_node.name)] = \
        [Link(dst_label=iodineSvr.address, src_label=resolver_node.name)]
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
    dnsquerytm = f'tm(tt:Float,to X({resolver.address}) from {raceboatCl.masClientAddress} : {dnsquery.to_maude()})'
    # NOTE: we duplicate the preNAT DNS messages from alice-raceboat-mas-client because we see one A query and one AAAA
    pp.other[f'add-to-sent(tm(tt:Float,to addr0:Address from {raceboatCl.masClientAddress} : c:Content))'] = f'{dnsquerytm} ; {dnsquerytm}'
    pp.other[
        f'add-to-sent(tm(tt:Float,to addr0:Address from Z(i:Nat, {raceboatCl.masClientAddress}) : c:Content))'] = f'tm(tt:Float,to {resolver.address} from Z(i:Nat, {raceboatCl.masClientAddress}) : {dnsquery.to_maude()})'

    C = CP3Config(
        [Ctr(hcsconf.seed), router], #, adversary],
        monitor, 
        [sndApp, rcvApp, mainSndApp, mainRcvApp],
        [iodineCl, iodineSvr, masServer, raceboatCl, raceboatSvr],
        clients,
        tgen_clients,
        [resolver],
        [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP],
        root_nameservers,
        parameterized_network,
        hcsconf.output.directory
    )
    ndp = {}
    pp = {}
    for pname,protocol in hcsconf.protocols.items():
        if protocol.nondeterministic_parameters:
            ndp |= protocol.nondeterministic_parameters.to_dict()
        if protocol.probabilistic_parameters:
            pp |= protocol.probabilistic_parameters.to_dict()
    C.set_params(ndp, pp)
    C.set_preamble(hcsconf.output.preamble)

    #C.set_model_type(_args.model)
    C.set_model_type("prob")

    return C