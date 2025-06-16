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

from maude_hcs.lib.dns.DNSConfig import DNSConfig
from Maude.attack_exploration.src.zone import Record, Zone
from Maude.attack_exploration.src.actors import Nameserver, Client
from Maude.attack_exploration.src.query import Query
from Maude.attack_exploration.src.network import *
from maude_hcs.lib.dns import DNS_GLOBALS
from typing import Tuple, List

from maude_hcs.parsers.dnshcsconfig import DNSHCSConfig
from maude_hcs.parsers.hcsconfig import HCSConfig
from .iodineActors import IResolver
from .cache import ResolverCache, CacheEntry
from maude_hcs.parsers.graph import find_node_name
from maude_hcs.parsers.shadowconf import *
import ast
import logging

logger = logging.getLogger(__name__)

def createAuthZone(domain_name: str, NAME:str, parent:Zone, num_records:int, TTL:int = 3600, TTL_A:int = 0) -> Tuple[Zone, List]:
        DNS_GLOBALS.counter += 1
        records = [Record(f'tmp{index}.{domain_name}', 'A', TTL_A, f'{DNS_GLOBALS.counter}.{index}.1.2') for index in range(num_records)]
        zone_records  = [Record(domain_name, 'SOA', TTL, f'{TTL}')]
        ns_records = [    
                Record(domain_name, 'NS', TTL, f'ns.{domain_name}'),
                Record(f'ns.{domain_name}', 'A', TTL, NAME)
            ]
        zone_records.extend(ns_records)
        zone_records.extend(records)
        # Append wildcard name
        zone_records.append(Record(f'*.{domain_name}', 'A', TTL_A, f'{DNS_GLOBALS.counter}.{num_records}.1.2'))
        return Zone(domain_name, parent, zone_records), ns_records

def createRootZone(hcsconf:DNSHCSConfig, TTL:int = 3600) -> Tuple[Zone, List]:
    # root zone    
    root_node = hcsconf.topology.getNodebyLabel(hcsconf.underlying_network.root_name)
    assert root_node, "Root node undefined"   
    tld_node = hcsconf.topology.getNodebyLabel(hcsconf.underlying_network.tld_name)
    assert tld_node, "TLD node undefined"   
    
    # zone apex
    records = [Record('', 'SOA', TTL, f'{TTL}')]
    ns_records = [
            Record('', 'NS', TTL, 'a.root-servers.net.'),
            # delegations and glue
            Record('a.root-servers.net.', 'A', TTL, root_node.address),            
    ]
    records.extend(ns_records)
    # non auth - glue 
    records.extend([
        Record(hcsconf.underlying_network.tld_domain, 'NS', TTL, f'ns.{hcsconf.underlying_network.tld_domain}'),
        Record(f'ns.{hcsconf.underlying_network.tld_domain}', 'A', TTL, tld_node.address),
        ])
    return Zone('', None, records), ns_records

def createTLDZone(hcsconf:DNSHCSConfig, zoneRoot, TTL:int = 3600) -> Tuple[Zone, List]:    
    root_node = hcsconf.topology.getNodebyLabel(hcsconf.underlying_network.root_name)
    assert root_node, "Root node undefined"   
    tld_node = hcsconf.topology.getNodebyLabel(hcsconf.underlying_network.tld_name)
    assert tld_node, "TLD node undefined"   
    ee_node = hcsconf.topology.getNodebyLabel(hcsconf.underlying_network.everythingelse_name)
    assert ee_node, "Everythingelse node undefined"
    pwnd2_node = hcsconf.topology.getNodebyLabel(hcsconf.underlying_network.pwnd2_name)
    assert pwnd2_node, "PWND2 node undefined"
    corp_node = hcsconf.topology.getNodebyLabel(hcsconf.underlying_network.corporate_name)
    assert corp_node, "Corp node undefined"
    tld_domain = hcsconf.underlying_network.tld_domain
    corp_domain = hcsconf.underlying_network.corporate_domain
    ee_domain = hcsconf.underlying_network.everythingelse_domain
    pwnd_domain = hcsconf.underlying_network.pwnd2_domain

    
    records = [Record(tld_domain, 'SOA', TTL, f'{TTL}')]
    ns_records = [
        Record(tld_domain, 'NS', TTL, f'ns.{tld_domain}'),
        Record(f'ns.{tld_domain}', 'A', TTL, tld_node.address)
    ]
    records.extend(ns_records)
    # non auth - glue
    records.extend([
        Record(ee_domain, 'NS', TTL, f'ns.{ee_domain}'),
        Record(f'ns.{ee_domain}', 'A', TTL, ee_node.address),
        Record(pwnd_domain, 'NS', TTL, f'ns.{pwnd_domain}'),
        Record(f'ns.{pwnd_domain}', 'A', TTL, pwnd2_node.address),
        Record(corp_domain, 'NS', TTL, f'ns.{corp_domain}'),
        Record(f'ns.{corp_domain}', 'A', TTL, corp_node.address)        
    ])
    # com TLD zone
    return Zone(tld_domain, zoneRoot, records), ns_records

def corporate(_args, run_args, shadow_conf:ShadowConfig = None) -> DNSConfig:
    # TODO: This mapping to shadow names, if available, should happen somewhereelse
    # and be passed already in the correct name.
    args = run_args["underlying_network"]
    num_records = args.get('everythingelse_num_records', 1)


    populateCache = args.get('populate_resolver_cache', False)
    record_ttl = args.get('record_ttl', 3600)

    links_args  = args.get("links")

    addr_prefix   = args.get("addr_prefix", "addrNS")
    links = args.get("links")
    if _args.topology_filename:
      args  = run_args.get("topology")
      node_names  = args["node_names"]
      edges_info  = args["edges_info"]
      parameterized_network = ParameterizedNetwork(edges_info)
      args        = run_args.get("underlying_network")
      EE_NAME     = find_node_name(node_names, [args.get("everythingelse_name", "example"), "internet"])
      CORP_NAME   =  find_node_name(node_names, [args.get("corporate_name", "corp"), "local"])
      resolver_name = find_node_name(node_names, [args.get("resolver_name", "rAddr"), "public"])
      PWND2_NAME  = find_node_name(node_names, [args.get("pwnd2_name", "pwnd2"), "server"])
      ROOT_NAME   = find_node_name(node_names, ["root"], default="root")
      COM_NAME  = find_node_name(node_names, ["com", "tld"], default="com")
      links = ast.literal_eval(str(links)
                   .replace("pwnd2_name", PWND2_NAME)
                   .replace("resolver_name", resolver_name)
                   .replace("corporate_name", CORP_NAME)
                   .replace("everythingelse_name", EE_NAME)
                   .replace("com", COM_NAME)
                   # Assume root is not named explicitly in our use case.
                   .replace("root", ROOT_NAME)
                 )
    else:
        EE_NAME       = args.get("everythingelse_name", "example")
        CORP_NAME     = args.get("corporate_name", "corp")
        resolver_name = args.get("resolver_name", "rAddr")
        PWND2_NAME    = args.get("pwnd2_name", "pwnd2")
        ROOT_NAME     = "root"
        COM_NAME      = "com"
        links = ast.literal_eval(str(links)
                     .replace("pwnd2_name", PWND2_NAME)
                     .replace("resolver_name", resolver_name)
                     .replace("corporate_name", CORP_NAME)
                     .replace("everythingelse_name", EE_NAME)
                     .replace("com", COM_NAME)
                     # Assume root is not named explicitly in our use case.
                     .replace("root", ROOT_NAME)
                   )
        parameterized_network = ParameterizedNetwork(links)

    ADDR_NS_ROOT  = f"{addr_prefix}{ROOT_NAME}"
    ADDR_NS_COM   = f"{addr_prefix}{COM_NAME}"
    
    cacheRecords = []
    # root zone

    zoneRoot, ns_records = createRootZone(args)
    cacheRecords.extend(ns_records)

    # com zone
    zoneCom, ns_records = createTLDZone(run_args, zoneRoot)
    cacheRecords.extend(ns_records)

    # EverythingElse EE zone
    zoneEverythingelse, ns_records = createAuthZone(EE_NAME, f"{addr_prefix}{EE_NAME}", zoneCom, num_records)
    cacheRecords.extend(ns_records)
    # PWND2 domain name may be different than PWND2 server name.
    # TODO: Grab it from the shadow file, if available.
    pwd2_domain_name  = run_args["underlying_network"].get("pwnd2_base_name")        
    zonepwnd2, ns_records = createAuthZone(pwd2_domain_name.rstrip(".com"), f"{addr_prefix}{PWND2_NAME}", zoneCom, num_records)  
    cacheRecords.extend(ns_records)
    zonecorp, ns_records = createAuthZone(CORP_NAME, f"{addr_prefix}{CORP_NAME}", zoneCom, num_records)
    cacheRecords.extend(ns_records)
    

    resolver = IResolver('rAddr')
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

    host_names = [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP, resolver, nameserverPWND2]
    parameterized_network.create_links(host_names, links)

    query = Query(1, f'www0.{EE_NAME}.com.', 'A')
    client = Client('cAddr', [query], nameserverCORP)    

    root_nameservers = {'a.root-servers.net.': ADDR_NS_ROOT}

    C = DNSConfig([client], [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverPWND2, nameserverCORP], root_nameservers, parameterized_network)
    C.set_params(run_args.get('nondeterministic_parameters', {}), run_args.get('probabilistic_parameters', {}))
    C.set_model_type(_args.model)
    return C
