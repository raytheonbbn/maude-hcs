from maude_hcs.lib.dns.IodineDNSConfig import IodineDNSConfig
from Maude.attack_exploration.src.actors import Resolver, Nameserver, Client
from Maude.attack_exploration.src.query import Query
from maude_hcs.lib.dns import GLOBALS
from maude_hcs.lib.dns.iodineActors import IodineClient, IodineServer, SendApp, ReceiveApp
from maude_hcs.lib.dns.utils import makePackets
from .corporate import createAuthZone, createRootZone, createTLDZone
import logging

logger = logging.getLogger(__name__)

def corporate_iodine(run_args) -> IodineDNSConfig:
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

    nameserverRoot = Nameserver(GLOBALS.ADDR_NS_ROOT, [zoneRoot])
    nameserverCom = Nameserver(GLOBALS.ADDR_NS_COM, [zoneCom])
    nameserverEE = Nameserver(f'addrNS{EE_NAME}', [zoneEverythingelse])
    nameserverCORP = Nameserver(f'addrNS{CORP_NAME}', [zonecorp], forwardonly=resolver.address)
    nameserverPWND2 = Nameserver(f'addrNS{PWND2_NAME}', [zonepwnd2])

    query = Query(1, f'www0.{EE_NAME}.com.', 'A')
    client = Client('cAddr', [query], nameserverCORP)

    root_nameservers = {'a.root-servers.net.': GLOBALS.ADDR_NS_ROOT}

    # tunnels and apps
    args = run_args["application"]
    pkt_sizes = args["send_app_queue_pkt_sizes"]
    aliceAddr = args['send_app_address']
    sndApp = SendApp(aliceAddr, makePackets(aliceAddr, pkt_sizes))
    rcvApp = ReceiveApp(args['rcv_app_address'])
    args = run_args["weird_network"]
    iodineCl = IodineClient(args['client_address'], args['client_weird_base_name'], args['client_weird_qtype'], nameserverCORP.address, sndApp)
    iodineSvr = IodineServer(f'addrNS{PWND2_NAME}', rcvApp, nameserverPWND2)

    C = IodineDNSConfig([], [iodineCl, iodineSvr], [client], [resolver], [nameserverRoot, nameserverCom, nameserverEE, nameserverCORP], root_nameservers)
    C.set_params(run_args.get('nondeterministic_parameters', {}))
    return C