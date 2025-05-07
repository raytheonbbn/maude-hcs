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
    # zone apex
    records = [Record('', 'SOA', TTL, f'{TTL}')]
    ns_records = [
            Record('', 'NS', TTL, 'a.root-servers.net.'),
            # delegations and glue
            Record('a.root-servers.net.', 'A', TTL, DNS_GLOBALS.ADDR_NS_ROOT),            
    ]
    records.extend(ns_records)
    # non auth - glue 
    records.extend([
        Record('com.', 'NS', TTL, 'ns.com.'),
        Record('ns.com.', 'A', TTL, DNS_GLOBALS.ADDR_NS_COM),
        ])
    return Zone('', None, records), ns_records

def createTLDZone(run_args, zoneRoot, TTL:int = 3600) -> Tuple[Zone, List]:
    args = run_args["underlying_network"]
    EE_NAME = args.get('everythingelse_name', 'everythingelse')
    PWND2_NAME = args.get('pwnd2_name', 'pwnd2')
    CORP_NAME = args.get('corporate_name', 'corp')

    records = [Record('com.', 'SOA', TTL, f'{TTL}')]
    ns_records = [
        Record('com.', 'NS', TTL, 'ns.com.'),
        Record('ns.com.', 'A', TTL, DNS_GLOBALS.ADDR_NS_COM),
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
    EE_NAME = args.get('everythingelse_name', 'everythingelse')
    PWND2_NAME = args.get('pwnd2_name', 'pwnd2')
    CORP_NAME = args.get('corporate_name', 'corp')
    num_records = args.get('everythingelse_num_records', 1)
    populateCache = args.get('populate_resolver_cache', False)
    record_ttl = args.get('record_ttl', 3600)
    
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

    nameserverRoot = Nameserver(DNS_GLOBALS.ADDR_NS_ROOT, [zoneRoot])
    nameserverCom = Nameserver(DNS_GLOBALS.ADDR_NS_COM, [zoneCom])
    nameserverEE = Nameserver(f'addrNS{EE_NAME}', [zoneEverythingelse])
    nameserverCORP = Nameserver(f'addrNS{CORP_NAME}', [zonecorp], forwardonly=resolver.address)
    nameserverPWND2 = Nameserver(f'addrNS{PWND2_NAME}', [zonepwnd2])

    query = Query(1, f'www0.{EE_NAME}.com.', 'A')
    client = Client('cAddr', [query], nameserverCORP)    

    root_nameservers = {'a.root-servers.net.': DNS_GLOBALS.ADDR_NS_ROOT}

    C = DNSConfig([client], [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverPWND2, nameserverCORP], root_nameservers)
    C.set_params(run_args.get('nondeterministic_parameters', {}), run_args.get('probabilistic_parameters', {}))
    C.set_model_type(_args.model)
    return C
