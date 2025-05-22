from maude_hcs.lib.dns.DNSConfig import DNSConfig
from Maude.attack_exploration.src.zone import Record, Zone
from Maude.attack_exploration.src.actors import Resolver, Nameserver, Client
from Maude.attack_exploration.src.query import Query
from Maude.attack_exploration.src.network import *
from maude_hcs.lib.dns import DNS_GLOBALS
from maude_hcs.parsers.graph import find_node_name
import ast
import logging

logger = logging.getLogger(__name__)

def createAuthZone(domain_name: str, NAME:str, parent:Zone, num_records:int) -> Zone:
        DNS_GLOBALS.counter += 1
        records = [Record(f'www{index}.{domain_name}.com.', 'A', 3600, f'{DNS_GLOBALS.counter}.{index}.1.2') for index in range(num_records)]
        zone_records  = [ 
            Record(f'{domain_name}.com.', 'SOA', 3600, '3600'),
            Record(f'{domain_name}.com.', 'NS', 3600, f'ns.{domain_name}.com.'),
            Record(f'ns.{domain_name}.com.', 'A', 3600, f'{NAME}')]
        zone_records.extend(records)
        zone_records.append(Record(f'*.{domain_name}.com.', 'TXT', 3600, '...'))
        return Zone(f'{domain_name}.com.', parent, zone_records)

def createRootZone(run_args) -> Zone:    
    # root zone
    # TODO: This mapping to shadow names, if available, should happen somewhereelse
    # and be passed already in the correct name.
    args        = run_args.get("topology")
    node_names  = args.get("node_names", None)
    addr_prefix = args.get("addr_prefix", "addrNS")
    ROOT_NAME   = find_node_name(node_names, ["root"], default="root")
    COM_NAME    = find_node_name(node_names, ["com", "tld"])
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
    # TODO: This mapping to shadow names, if available, should happen somewhereelse
    # and be passed already in the correct name.
    args          = run_args.get("topology")
    node_names    = args.get("node_names", None)
    addr_prefix   = args.get("addr_prefix", "addrNS")
    EE_NAME       = find_node_name(node_names, ["example", "internet"])
    CORP_NAME     = find_node_name(node_names, ["corp", "local"])
    PWND2_NAME    = find_node_name(node_names, ["pwnd2", "server"])
    COM_NAME      = find_node_name(node_names, ["com", "tld"])
    ADDR_NS_COM   = f"{addr_prefix}{COM_NAME}"
    pwnd_basename = run_args.get("underlying_network").get("pwnd2_base_name").rstrip(".com")

    # com TLD zone
    return Zone('com.', zoneRoot,
        [
            Record('com.', 'SOA', 3600, '3600'),
            Record('com.', 'NS', 3600, 'ns.com.'),
            Record('ns.com.', 'A', 3600, ADDR_NS_COM),

            # delegations and glue
            Record(f'{EE_NAME}.com.', 'NS', 3600, f'ns.{EE_NAME}.com.'),
            Record(f'ns.{EE_NAME}.com.', 'A', 3600, f'addrNS{EE_NAME}'),
            Record(f'{pwnd_basename}.com.', 'NS', 3600, f'ns.{pwnd_basename}.com.'),
            Record(f'ns.{pwnd_basename}.com.', 'A', 3600, f'addrNS{PWND2_NAME}'),
            Record(f'{CORP_NAME}.com.', 'NS', 3600, f'ns.{CORP_NAME}.com.'),
            Record(f'ns.{CORP_NAME}.com.', 'A', 3600, f'addrNS{CORP_NAME}'),
        ])

def corporate(_args, run_args) -> DNSConfig:
    # TODO: This mapping to shadow names, if available, should happen somewhereelse
    # and be passed already in the correct name.
    args = run_args["underlying_network"]
    num_records = args.get('everythingelse_num_records', 1)
    addr_prefix   = args.get("addr_prefix", "addrNS")
    links = args.get("links")
    if not _args.topology_filename is None:
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
    
    # root zone
    zoneRoot = createRootZone(run_args)

    # com zone
    zoneCom = createTLDZone(run_args, zoneRoot)

    # EverythingElse EE zone
    zoneEverythingelse = createAuthZone(EE_NAME, f"{addr_prefix}{EE_NAME}", zoneCom, num_records)
    # PWND2 domain name may be different than PWND2 server name.
    # TODO: Grab it from the shadow file, if available.
    pwd2_domain_name  = run_args["underlying_network"].get("pwnd2_base_name")
    zonepwnd2 = createAuthZone(pwd2_domain_name.rstrip(".com"), f"{addr_prefix}{PWND2_NAME}", zoneCom, num_records)  
    zonecorp = createAuthZone(CORP_NAME, f"{addr_prefix}{CORP_NAME}", zoneCom, num_records)
    
    resolver = Resolver(resolver_name) 

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
