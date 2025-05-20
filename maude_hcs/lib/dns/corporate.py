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
from maude_hcs.lib.dns import DNS_GLOBALS
from typing import Tuple, List
from .iodineActors import IResolver
from .cache import ResolverCache, CacheEntry
from maude_hcs.parsers.graph import find_node_name
import logging

logger = logging.getLogger(__name__)

def createAuthZone(NAME:str, parent:Zone, num_records:int, TTL:int = 3600) -> Tuple[Zone, List]:
        DNS_GLOBALS.counter += 1
        records = [Record(f'www{index}.{NAME}.com.', 'A', TTL, f'{DNS_GLOBALS.counter}.{index}.1.2') for index in range(num_records)]
        zone_records  = [Record(f'{NAME}.com.', 'SOA', TTL, f'{TTL}')]
        ns_records = [    
                Record(f'{NAME}.com.', 'NS', TTL, f'ns.{NAME}.com.'),
                Record(f'ns.{NAME}.com.', 'A', TTL, f'addrNS{NAME}')
            ]
        zone_records.extend(ns_records)
        zone_records.extend(records)
        zone_records.append(Record(f'*.{NAME}.com.', 'TXT', TTL, '...'))
        return Zone(f'{NAME}.com.', parent, zone_records), ns_records

def createRootZone(run_args, TTL:int = 3600) -> Tuple[Zone, List]:
    # root zone
    args        = run_args
    node_names  = args.get("node_names")
    addr_prefix = args.get("addr_prefix", "addrNS")
    ROOT_NAME   = find_node_name(node_names, ["root"])
    COM_NAME    = find_node_name(node_names, ["com", "internet"])
    ADDR_NS_ROOT= f"{addr_prefix}{ROOT_NAME}"
    ADDR_NS_COM = f"{addr_prefix}{COM_NAME}"
    # zone apex
    records = [Record('', 'SOA', TTL, f'{TTL}')]
    ns_records = [
            Record('', 'NS', TTL, 'a.root-servers.net.'),
            # delegations and glue
            Record('a.root-servers.net.', 'A', TTL, ADDR_NS_ROOT),            
    ]
    records.extend(ns_records)
    # non auth - glue 
    records.extend([
        Record('com.', 'NS', TTL, 'ns.com.'),
        Record('ns.com.', 'A', TTL, ADDR_NS_COM),
        ])
    return Zone('', None, records), ns_records


def createTLDZone(run_args, zoneRoot, TTL:int = 3600) -> Tuple[Zone, List]:
    args          = run_args.get("topology")
    node_names    = args.get("node_names")
    addr_prefix   = args.get("addr_prefix", "addrNS")
    EE_NAME       = find_node_name(node_names, ["everythingelse", "internet"])
    CORP_NAME     = find_node_name(node_names, ["corp", "local"])
    PWND2_NAME    = find_node_name(node_names, ["pwnd2", "tld"])
    COM_NAME      = find_node_name(node_names, ["com", "internet"])
    ADDR_NS_COM   = f"{addr_prefix}{COM_NAME}"
    
    records = [Record('com.', 'SOA', TTL, f'{TTL}')]
    ns_records = [
        Record('com.', 'NS', TTL, 'ns.com.'),
        Record('ns.com.', 'A', TTL, ADDR_NS_COM),
    ]
    records.extend(ns_records)
    # non auth - glue
    records.extend([
        Record(f'{EE_NAME}.com.', 'NS', TTL, f'ns.{EE_NAME}.com.'),
        Record(f'ns.{EE_NAME}.com.', 'A', TTL, f'addrNS{EE_NAME}'),
        Record(f'{PWND2_NAME}.com.', 'NS', TTL, f'ns.{PWND2_NAME}.com.'),
        Record(f'ns.{PWND2_NAME}.com.', 'A', TTL, f'addrNS{PWND2_NAME}'),
        Record(f'{CORP_NAME}.com.', 'NS', TTL, f'ns.{CORP_NAME}.com.'),
        Record(f'ns.{CORP_NAME}.com.', 'A', TTL, f'addrNS{CORP_NAME}'),
    ])
    # com TLD zone

    return Zone('com.', zoneRoot, records), ns_records

def corporate(_args, run_args) -> DNSConfig:
    args = run_args["underlying_network"]
    num_records = args.get('everythingelse_num_records', 1)

    populateCache = args.get('populate_resolver_cache', False)
    record_ttl = args.get('record_ttl', 3600)

    links_args  = args.get("links")
    addr_prefix   = args.get("addr_prefix", "addrNS")
    args          = run_args.get("topology")
    node_names    = args.get("node_names")
    EE_NAME       = find_node_name(node_names, ["everythingelse", "internet"])
    CORP_NAME     = find_node_name(node_names, ["corp", "local"])
    PWND2_NAME    = find_node_name(node_names, ["pwnd2", "tld"])
    resolver_name = find_node_name(node_names, ["rAddr", "public"])
    ROOT_NAME     = find_node_name(node_names, ["root"])
    COM_NAME      = find_node_name(node_names, ["com", "internet"])
    ADDR_NS_ROOT  = f"{addr_prefix}{ROOT_NAME}"
    ADDR_NS_COM   = f"{addr_prefix}{COM_NAME}"

    link_characteristics  = run_args["link_characteristics"]
    
    cacheRecords = []
    # root zone
    zoneRoot, ns_records = createRootZone(args)
    cacheRecords.extend(ns_records)

    # com zone
    zoneCom, ns_records = createTLDZone(run_args, zoneRoot)
    cacheRecords.extend(ns_records)

    # EverythingElse EE zone
    zoneEverythingelse, ns_records = createAuthZone(EE_NAME, zoneCom, num_records)
    cacheRecords.extend(ns_records)
    zonepwnd2, ns_records = createAuthZone(PWND2_NAME, zoneCom, num_records)  
    cacheRecords.extend(ns_records)
    zonecorp, ns_records = createAuthZone(CORP_NAME, zoneCom, num_records)
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

    query = Query(1, f'www0.{EE_NAME}.com.', 'A')
    client = Client('cAddr', [query], nameserverCORP)    

    root_nameservers = {'a.root-servers.net.': ADDR_NS_ROOT}

    C = DNSConfig([client], [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverPWND2, nameserverCORP], root_nameservers)
    C.set_params(run_args.get('nondeterministic_parameters', {}), run_args.get('probabilistic_parameters', {}))
    C.set_model_type(_args.model)
    return C
