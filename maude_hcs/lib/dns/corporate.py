from maude_hcs.lib.dns.DNSConfig import DNSConfig
from Maude.attack_exploration.src.zone import Record, Zone
from Maude.attack_exploration.src.actors import Resolver, Nameserver, Client
from Maude.attack_exploration.src.query import Query
from maude_hcs.lib.dns import DNS_GLOBALS
from maude_hcs.parsers.graph import find_node_name
import logging

logger = logging.getLogger(__name__)

def createAuthZone(NAME:str, parent:Zone, num_records:int) -> Zone:
        DNS_GLOBALS.counter += 1
        records = [Record(f'www{index}.{NAME}.com.', 'A', 3600, f'{DNS_GLOBALS.counter}.{index}.1.2') for index in range(num_records)]
        zone_records  = [ 
            Record(f'{NAME}.com.', 'SOA', 3600, '3600'),
            Record(f'{NAME}.com.', 'NS', 3600, f'ns.{NAME}.com.'),
            Record(f'ns.{NAME}.com.', 'A', 3600, f'addrNS{NAME}')]
        zone_records.extend(records)
        zone_records.append(Record(f'*.{NAME}.com.', 'TXT', 3600, '...'))
        return Zone(f'{NAME}.com.', parent, zone_records)

def createRootZone(run_args) -> Zone:    
    # root zone
    args        = run_args
    node_names  = args.get("node_names")
    addr_prefix = args.get("addr_prefix", "addrNS")
    ROOT_NAME   = find_node_name(node_names, ["root"])
    COM_NAME    = find_node_name(node_names, ["com", "internet"])
    ADDR_NS_ROOT= f"{addr_prefix}{ROOT_NAME}"
    ADDR_NS_COM = f"{addr_prefix}{COM_NAME}"
    return Zone('', None,
        [
            # zone apex
            Record('', 'SOA', 3600, '3600'),
            Record('', 'NS', 3600, 'a.root-servers.net.'),

            # delegations and glue
            Record('a.root-servers.net.', 'A', 3600, ADDR_NS_ROOT),
            Record('com.', 'NS', 3600, 'ns.com.'),
            Record('ns.com.', 'A', 3600, ADDR_NS_COM),
        ])

def createTLDZone(run_args, zoneRoot) -> Zone:
    #args = run_args["underlying_network"]
    #EE_NAME = args.get('everythingelse_name', 'everythingelse')
    #PWND2_NAME = args.get('pwnd2_name', 'pwnd2')
    #CORP_NAME = args.get('corporate_name', 'corp')
    args          = run_args.get("topology")
    node_names    = args.get("node_names")
    addr_prefix   = args.get("addr_prefix", "addrNS")
    EE_NAME       = find_node_name(node_names, ["everythingelse", "internet"])
    CORP_NAME     = find_node_name(node_names, ["corp", "local"])
    PWND2_NAME    = find_node_name(node_names, ["pwnd2", "tld"])
    COM_NAME      = find_node_name(node_names, ["com", "internet"])
    ADDR_NS_COM   = f"{addr_prefix}{COM_NAME}"

    # com TLD zone
    return Zone('com.', zoneRoot,
        [
            Record('com.', 'SOA', 3600, '3600'),
            Record('com.', 'NS', 3600, 'ns.com.'),
            Record('ns.com.', 'A', 3600, ADDR_NS_COM),

            # delegations and glue
            Record(f'{EE_NAME}.com.', 'NS', 3600, f'ns.{EE_NAME}.com.'),
            Record(f'ns.{EE_NAME}.com.', 'A', 3600, f'addrNS{EE_NAME}'),
            Record(f'{PWND2_NAME}.com.', 'NS', 3600, f'ns.{PWND2_NAME}.com.'),
            Record(f'ns.{PWND2_NAME}.com.', 'A', 3600, f'addrNS{PWND2_NAME}'),
            Record(f'{CORP_NAME}.com.', 'NS', 3600, f'ns.{CORP_NAME}.com.'),
            Record(f'ns.{CORP_NAME}.com.', 'A', 3600, f'addrNS{CORP_NAME}'),
        ])

def corporate(_args, run_args) -> DNSConfig:
    args = run_args["underlying_network"]
    #EE_NAME = args.get('everythingelse_name', 'everythingelse')
    #PWND2_NAME = args.get('pwnd2_name', 'pwnd2')
    #CORP_NAME = args.get('corporate_name', 'corp')
    num_records = args.get('everythingelse_num_records', 1)
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
    
    # root zone
    zoneRoot = createRootZone(args)

    # com zone
    zoneCom = createTLDZone(run_args, zoneRoot)

    # EverythingElse EE zone
    zoneEverythingelse = createAuthZone(EE_NAME, zoneCom, num_records)
    zonepwnd2 = createAuthZone(PWND2_NAME, zoneCom, num_records)  
    zonecorp = createAuthZone(CORP_NAME, zoneCom, num_records)
    
    #resolver = Resolver('rAddr')    

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
