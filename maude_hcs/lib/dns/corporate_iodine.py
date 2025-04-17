from maude_hcs.lib.dns.IodineDNSConfig import IodineDNSConfig
from Maude.attack_exploration.src.actors import Resolver, Nameserver, Client
from Maude.attack_exploration.src.query import Query
from maude_hcs.lib.dns import DNS_GLOBALS
from maude_hcs.lib.dns.iodineActors import IodineClient, IodineServer, SendApp, ReceiveApp, WMonitor
from maude_hcs.lib.dns.utils import makePackets
from .corporate import createAuthZone, createRootZone, createTLDZone
import logging

logger = logging.getLogger(__name__)

def corporate_iodine(_args, run_args) -> IodineDNSConfig:
    args = run_args["underlying_network"]
    EE_NAME = args.get('everythingelse_name', 'everythingelse')
    PWND2_NAME = args.get('pwnd2_name', 'pwnd2')
    CORP_NAME = args.get('corporate_name', 'corp')
    num_records = args.get('everythingelse_num_records', 1)
    
    # root zone
    zoneRoot = createRootZone(args)

    # com zone
    zoneCom = createTLDZone(run_args, zoneRoot)

    # EverythingElse EE zone
    zoneEverythingelse = createAuthZone(EE_NAME, zoneCom, num_records)
    zonepwnd2 = createAuthZone(PWND2_NAME, zoneCom, num_records)  
    zonecorp = createAuthZone(CORP_NAME, zoneCom, num_records)
    
    resolver = Resolver('rAddr')    

    nameserverRoot = Nameserver(DNS_GLOBALS.ADDR_NS_ROOT, [zoneRoot])
    nameserverCom = Nameserver(DNS_GLOBALS.ADDR_NS_COM, [zoneCom])
    nameserverEE = Nameserver(f'addrNS{EE_NAME}', [zoneEverythingelse])
    nameserverCORP = Nameserver(f'addrNS{CORP_NAME}', [zonecorp], forwardonly=resolver.address)
    nameserverPWND2 = Nameserver(f'addrNS{PWND2_NAME}', [zonepwnd2])

    
    root_nameservers = {'a.root-servers.net.': DNS_GLOBALS.ADDR_NS_ROOT}

    # tunnels 
    args = run_args["weird_network"]
    iodineClAddr = args['client_address']
    iodineCl = IodineClient(iodineClAddr, args['client_weird_base_name'], args['client_weird_qtype'], nameserverCORP.address)
    iodineSvr = IodineServer(f'addrNS{PWND2_NAME}', nameserverPWND2)
    monitorAddr = args.get('monitor_address', DNS_GLOBALS.ADDR_MONITOR)
    # applications
    args = run_args["application"]
    pkt_sizes = args["send_app_queue_pkt_sizes"]
    aliceAddr = args['send_app_address']
    bobAddr = args['rcv_app_address']    
    start_send_app = float(args["app_start_send_time"])
    include_dns_client = args['include_dns_client']
    # app sends packets to the iodineClAddr
    sndApp = SendApp(aliceAddr, iodineClAddr, makePackets(aliceAddr, bobAddr, pkt_sizes), start_send_app)
    rcvApp = ReceiveApp(bobAddr)
    
    # monitor
    monitor = WMonitor(monitorAddr)
    
    clients = []
    if include_dns_client:
        query = Query(1, f'www0.{EE_NAME}.com.', 'A')
        clients.append( Client('cAddr', [query], nameserverCORP) )

    C = IodineDNSConfig(monitor, [sndApp, rcvApp], [iodineCl, iodineSvr], clients, [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP], root_nameservers)
    C.set_params(run_args.get('nondeterministic_parameters', {}), run_args.get('probabilistic_parameters', {}))
    C.set_model_type(_args.model)
    return C