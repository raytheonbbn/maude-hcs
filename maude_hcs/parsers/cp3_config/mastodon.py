from .common import Address, Node, Link, LinkType, Counter, TGenType, TGenConfig, Topology, indent, profile_to_maude

def insert_mastodon_tgens(
    tgen_cfgs: list[TGenConfig],
    topo: Topology,
    mastodon_server: Node,
    mastodon_server_linktypes: tuple[LinkType, LinkType],
    subnet_idx: int):

  for i, tgen_cfg in enumerate(tgen_cfgs):
    mast_tgen_addr = Address(f"mast-tgen-addr-{i}", f"a(cl[{subnet_idx}],tgen,mas,app,1)") # TODO: what does this actually represent?
    mast_tgen_usermodel_addr = Address(f"mast-tgen-usermodel-addr-{i}", f"a(cl[{subnet_idx}],tgen,mas,um,1)")
    mast_client_addr = Address(f"mast-client-addr-{i}", f"a(cl[{subnet_idx}],tgen,mas,cl,1)")

    maude_prof = profile_to_maude(tgen_cfg.profile)
    mast_tgen = Node(
      mast_tgen_addr,
      f"mast-tgen-{i}",
      f"mkMasTGenActor({mast_tgen_addr.name}, {mast_client_addr.name}, ed-images, {maude_prof})")
    mast_tgen_usermodel = Node(
      mast_tgen_usermodel_addr,
      f"mast-tgen-usermodel-{i}",
      f"mkUMactor({mast_tgen_usermodel_addr.name}, {maude_prof}, {mast_tgen_addr.name})")
    mast_client = Node(
      mast_client_addr,
      f"mast-client-{i}",
      f"makeMastodonClient({mast_client_addr.name}, {mastodon_server.addr.name}, {mast_tgen_addr.name})")

    # TODO: fix this! this node doesn't use a predefined address for some reason idk
    mast_tgen_netclient = Node(
      Address("temp", f"a(cl[{subnet_idx}],tcp,mas,cl,1)"),
      f"mast-tgen-netclient-{i}",
      f"makeNetClient(a(cl[{subnet_idx}],tcp,mas,cl,1), {mastodon_server.addr.name}, {mast_client_addr.name}, true, nullAddr, nullName)")

    client_uplink, client_downlink = tgen_cfg.uplink, tgen_cfg.downlink
    mast_uplink, mast_downlink = mastodon_server_linktypes
    print(mast_uplink)
    print(mast_downlink)
    tgen_uplink, tgen_downlink = client_uplink.combine(mast_downlink), mast_uplink.combine(client_downlink)
    links = [
      Link(mast_client, mastodon_server, tgen_uplink),
      Link(mastodon_server, mast_client, tgen_downlink),
      Link(mast_client, None, client_uplink),
      Link(None, mast_client, client_downlink),
    ]

    topo.nodes.extend([mast_tgen, mast_tgen_usermodel, mast_client, mast_tgen_netclient])
    topo.links.extend(links)

def mk_mastodon_topo(
    yml_subnets: dict, 
    yml_nodes: dict,
    subnet_linktypes: dict[str, LinkType],
    irc_server: Node,
    subnet_idx: int,
) -> tuple[Topology, Node, list[Address]]:
  """
  Create the chunk of the final network topology corresponding to (most) Mastodon traffic.
  This means the entire mastodon server subnet, the HCS actors in the client mastodon subnet, and the links between them and the IXP
  DOES NOT INCLUDE TGENS, since those are spread throughout all the networks.
  They are added to the final network topology in a separate step, using the returned mastodon server node.

  Returns:
    - the topology chunk for mastodon traffic
    - the node for the mastodon server (for use in tgen step)
    - a list of all client addresses in this chunk (for finale maude output)
  """

  nodes = []

  # Create the static actor addresses (these are always basically the same, regardless of how many active hcs clients there are)
  mast_server_iface_addr = Address("mast-server-iface-addr", f"a(srvN[{subnet_idx}],hcs,irc,if,1)") # No, this is for IRC side
  # This should be irc_server_mast_iface

  # These are all for IRC Side
  mast_umas_addr = Address("mast-umas-addr", f"a(srvN[{subnet_idx}],hcs,mas,um,1)")
  mast_cmas_addr = Address("mast-cmas-addr", f"a(srvN[{subnet_idx}],hcs,mas,cm,1)")
  mast_mcas_addr = Address("mast-mcas-addr", f"a(srvN[{subnet_idx}],hcs,mas,mc,1)")
  mast_edas_addr = Address("mast-edas-addr", f"a(srvN[{subnet_idx}],hcs,mas,ed,1)")
  # Should be irc_server_mast_usermodel_addr
  # irc_server_mast_cmgr_addr
  # irc_server_mast_mastclient_addr
  # irc_server_mast_destini_addr

  # this is also on IRC side, can tell by fact is uses srvN
  mast_server_netclient_addr = Address("mast-server-netclient-addr", f"a(srvN[{subnet_idx}],tcp,mas,cl,1)")


  mast_server_addr = Address("mast-server-addr", f"a(masN,tcp,mas,srv,1)")
  mast_subnet_router_addr = Address("mast-subnet-router-addr", f"a(masN,srv,mas,srv,1)")

  # Create the actual static actors
  mast_server_iface = Node(
    mast_server_iface_addr, 
    "mast-server-iface", 
    f"mkIrcByteSeqIface({mast_server_iface_addr.name}, {irc_server.addr.name}, {mast_cmas_addr.name})")
  mast_umas = Node(
    mast_umas_addr,
    "mast-umas",
    f"mkUMactor({mast_umas_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmas_addr.name})")
  mast_cmas = Node(
    mast_cmas_addr,
    "mast-cmas",
    f'mkCMSndRcvActor({mast_cmas_addr.name}, {mast_edas_addr.name}, {mast_mcas_addr.name}, {mast_server_iface_addr.name}, "server5", "client5")')
  mast_mcas = Node(
    mast_mcas_addr,
    "mast-mcas",
    f"makeMastodonClient({mast_mcas_addr.name}, {mast_subnet_router_addr.name}, {mast_cmas_addr.name})")
  mast_edas = Node(
    mast_edas_addr,
    "mast-edas",
    f"makeDestiniActor({mast_edas_addr.name}, ed-iamges)")
  mast_server = Node(
    mast_server_addr,
    "mast-server",
    f"makeNetServer({mast_server_addr.name}, {mast_subnet_router_addr.name})")
  mast_server_netclient = Node(
    mast_server_netclient_addr,
    "mast-server-netclient",
    f"makeNetClient({mast_server_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcas_addr.name}, true, nullAddr, nullName)")
  mast_subnet_router = Node(
    mast_subnet_router_addr,
    "mast-subnet-router",
    f"makeMastodonServer({mast_subnet_router_addr.name})")

  nodes += [mast_server_iface, mast_umas, mast_cmas, mast_mcas, mast_edas, mast_server, mast_server_netclient, mast_subnet_router]

  hcs_config = yml_nodes["node_type_mastodon"]
  num_hcs_clients = hcs_config["client_per_network"]["client_net_mastodon"]["quantity"]

  client_nodes: dict[str, Node] = {}
  client_addrs: list[Address] = []

  for i in range(num_hcs_clients):
    mast_client_addr = Address(f"mast-client-addr-{i}", f"a(cl[{subnet_idx}],hcs,irc,cl,{i})")
    mast_client_user_model_addr = Address(f"mast-client-user-model-addr-{i}", f"a(cl[{subnet_idx}],hcs,irc,um,{i})")
    mast_client_iface_addr = Address(f"mast-client-iface-addr-{i}", f"a(cl[{subnet_idx}],hcs,irc,if,{i})")
    mast_umac_addr = Address(f"mast-umac-addr-{i}", f"a(cl[{subnet_idx}],hcs,mas,um,{i})")
    mast_cmac_addr = Address(f"mast-cmac-addr-{i}", f"a(cl[{subnet_idx}],hcs,mas,cm,{i})")
    mast_mcac_addr = Address(f"mast-mcac-addr-{i}", f"a(cl[{subnet_idx}],hcs,mas,mc,{i})")
    mast_edac_addr = Address(f"mast-edac-addr-{i}", f"a(cl[{subnet_idx}],hcs,mas,ed,{i})")
    mast_client_netclient_addr = Address(f"mast-client-netclient-addr-{i}", f"a(cl[{subnet_idx}],tcp,mas,cl,{i})")
    client_addrs.append(mast_client_addr)

    named_nodes = {
      f"mast-client-{i}": Node(
        mast_client_addr, 
        f"mast-client-{i}", 
        f'mkIrcClient-v2({mast_client_addr.name}, {mast_client_iface_addr.name}, "Client{subnet_idx}")'),
      
      f"mast-client-user-model-{i}": Node(
        mast_client_user_model_addr, 
        f"mast-client-user-model-{i}", 
        f'mkIrcUMV2Actor({mast_client_user_model_addr.name}, "irc-test", {mast_client_addr.name})'),

      f"mast-client-iface-{i}": Node(
        mast_client_iface_addr, 
        f"mast-client-iface-{i}", 
        f"mkIrcByteSeqIface({mast_client_iface_addr.name}, {mast_client_addr.name}, {mast_cmac_addr.name})"),

      f"mast-umac-{i}": Node(
        mast_umac_addr, 
        f"mast-umac-{i}", 
        f"mkUMactor({mast_umac_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmac_addr.name})"),

      f"mast-cmac-{i}": Node(
        mast_cmac_addr, 
        f"mast-cmac-{i}", 
        f'mkCMSndRcvActor({mast_cmac_addr.name}, {mast_edac_addr.name}, {mast_mcac_addr.name}, {mast_client_iface_addr.name}, "mast-client-{i}", "mast-server")'),

      f"mast-mcac-{i}": Node(
        mast_mcac_addr, 
        f"mast-mcac-{i}", 
        f"makeMastodonClient({mast_mcac_addr.name}, {mast_subnet_router_addr.name}, {mast_cmac_addr.name})"),

      f"mast-edac-{i}": Node(
        mast_edac_addr, 
        f"mast-edac-{i}", 
        f"makeDestiniActor({mast_edac_addr.name}, ed-images)"),

      f"mast-client-netclient-{i}": Node(
        mast_client_netclient_addr, 
        f"mast-client-netclient-{i}", 
        f"makeNetClient({mast_client_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcac_addr.name}, true, nullAddr, nullName)"),
    }

    nodes += named_nodes.values()
    client_nodes.update(named_nodes)

  # server_subnet_config = yml_subnets["mastodon_net"]["params"]
  
  # server_up_latency = server_subnet_config["upstream"]["latency"]
  # server_down_latency = server_subnet_config["downstream"]["latency"]

  # server_up_loss = loss_specs[server_subnet_config["upstream"]["loss_profile"]]
  # server_down_loss = loss_specs[server_subnet_config["downstream"]["loss_profile"]]

  # TODO: give these the proper linktypes! Ask Christophe exactly how to combine probabilities
  links = [
    Link(mast_subnet_router, mast_mcas),
    Link(mast_mcas, mast_subnet_router),
    Link(mast_subnet_router, None),
    Link(None, mast_subnet_router),
    Link(mast_mcas, None),
    Link(None, mast_mcas),
  ]

  # client_subnet_config = yml_subnets["client_net_mastodon"]["params"]

  # client_up_latency = client_subnet_config["upstream"]["latency"]
  # client_down_latency = client_subnet_config["downstream"]["latency"]

  # client_up_loss = loss_specs[client_subnet_config["upstream"]["loss_profile"]]
  # client_down_loss = loss_specs[client_subnet_config["downstream"]["loss_profile"]]

  for i in range(num_hcs_clients):
    links += [
      Link(client_nodes[f"mast-mcac-{i}"], None),
      Link(None, client_nodes[f"mast-mcac-{i}"]),

      Link(mast_subnet_router, client_nodes[f"mast-mcac-{i}"]),
      Link(client_nodes[f"mast-mcac-{i}"], mast_subnet_router),
    ]

  return (Topology(True, nodes, links), mast_server, client_addrs)

  # Addrs
  # eq ircClient4Addr = a(cl[4],hcs,irc,cl,1) .
  # eq ircClient4UserModelAddr = a(cl[4],hcs,irc,um,1) .
  # eq client4IfaceAddr = a(cl[4],hcs,irc,if,1) .
  # eq serverIface4Addr = a(srvN[4],hcs,irc,if,1) .
  # eq sendApp4Addr = a(cl[4],hcs,iod,app,1) .
  # eq iodineClient4Addr = a(cl[4],hcs,iod,cl,1) .
  # eq rcvApp4Addr = a(srvN[4],hcs,iod,app,1) .
  # eq serverIodineServer4Addr = a(srvN[4],hcs,iod,iodSrv,1) .
  # eq iodineClient4NetClientAddr = a(cl[4],tcp,iod,cl,1) .
  # eq iodineServer4NetServerAddr = a(srvN[4],tcp,iod,srv,1) .

  # Clients
  # eq ircClient4          = mkIrcClient-v2(ircClient4Addr, client4IfaceAddr, "Client4") .
  # eq ircClient4UserModel = mkIrcUMV2Actor(ircClient4UserModelAddr, "irc-test", ircClient4Addr) .
  # eq client4Iface        = mkIrcByteSeqIface(client4IfaceAddr, ircClient4Addr, sendApp4Addr) .
  # eq serverIface4        = mkIrcByteSeqIface(serverIface4Addr, ircServerAddr, rcvApp4Addr) .
  # eq sendApp4            = mkSendApp(sendApp4Addr, rcvApp4Addr, client4IfaceAddr, iodineClient4Addr) .
  # eq rcvApp4             = mkRcvApp(rcvApp4Addr, sendApp4Addr, serverIface4Addr, iodineClient4Addr) .
  # eq iodineClient4       = makeWClient(iodineClient4Addr, serverIodineServer4Addr, 'pwnd2 . 'com . root, a, 0.0) .
  # eq serverIodineServer4 = makeWNameServer(serverIodineServer4Addr, 0.0, zonePwnd2Com4) .
  # eq iodineClient4NetClient = makeNetClient(iodineClient4NetClientAddr, serverIodineServer4Addr, iodineClient4Addr, true, nullAddr, nullName) .
  # eq iodineServer4NetServer = makeNetServer(iodineServer4NetServerAddr, serverIodineServer4Addr) .
  # eq iodineMonitor       = mkWMonitor(iodineMonitorAddr) .

  # Links
  # aaa(serverIodineServer4Addr, iodineClient4Addr, LinkType-TCP-4stateLoss)
  # aaa(iodineClient4Addr, serverIodineServer4Addr, LinkType-TCP-4stateLoss) 

# def mk_iodine_topo(
#     yml_subnets: Dict[Any, Any], 
#     yml_nodes: Dict[Any, Any],
#     subnet_linktypes: Dict[str, LinkType],
#     irc_server: Node,
#     subnet_idx: int,
# ) -> tuple[Topology, Node, list[Address]]:
#   """
#   See mk_mastodon_topo.
#   """

#   nodes = []

#   # eq serverIface4Addr = a(srvN[4],hcs,irc,if,1) .
#   # eq rcvApp4Addr = a(srvN[4],hcs,iod,app,1) .jj
#   # eq serverIodineServer4Addr = a(srvN[4],hcs,iod,iodSrv,1) .
#   # eq iodineServer4NetServerAddr = a(srvN[4],tcp,iod,srv,1) .

#   # Create the static actor addresses (these are always basically the same, regardless of how many active hcs clients there are)
#   iod_server_iface_addr = Address("iod_server_iface_addr", f"a(srvN[{subnet_idx}],hcs,irc,if,1)")
#   iod_server_rcv_app_addr = Address("iod_server_rcv_app_addr", f"a(srvN[{subnet_idx}],hcs,iod,app,1)")
#   iod_server_addr = Address("iod_server_addr", f"a(srvN[{subnet_idx}],hcs,iod,iodSrv,1)")
#   iod_server_netserver_addr = Address("iod_server_netserver_addr", f"a(srvN[{subnet_idx}],tcp,iod,srv,1)")


#   iod_server_iface = Node(iod_server_iface_addr, "iod_server_iface", f"mkIrcByteSeqIface({iod_server_iface_addr}, {iod_server_addr}, {iod_server_rcv_app_addr}) .")
#   iod_server_rcv_app = Node(iod_server_rcv_app_addr, "iod_server_rcv_app", f"mkRcvApp({iod_server_rcv_app_addr}, sendApp4Addr, serverIface4Addr, iodineClient4Addr) .")
#   iod_server = Node(iod_server_addr, "iod_server", f"makeWNameServer(serverIodineServer4Addr, 0.0, zonePwnd2Com4) .")
#   iod_server_netserver = Node(iod_server_netserver_addr, "iod_server_netserver", f"makeNetServer(iodineServer4NetServerAddr, serverIodineServer4Addr) .")

#   # eq serverIface4        = mkIrcByteSeqIface(serverIface4Addr, ircServerAddr, rcvApp4Addr) .
#   # eq rcvApp4             = mkRcvApp(rcvApp4Addr, sendApp4Addr, serverIface4Addr, iodineClient4Addr) .
#   # eq serverIodineServer4 = makeWNameServer(serverIodineServer4Addr, 0.0, zonePwnd2Com4) .
#   # eq iodineServer4NetServer = makeNetServer(iodineServer4NetServerAddr, serverIodineServer4Addr) .

#   # eq iodineMonitor       = mkWMonitor(iodineMonitorAddr) .



#   # eq ircClient4Addr = a(cl[4],hcs,irc,cl,1) .
#   # eq ircClient4UserModelAddr = a(cl[4],hcs,irc,um,1) .
#   # eq client4IfaceAddr = a(cl[4],hcs,irc,if,1) .
#   # eq sendApp4Addr = a(cl[4],hcs,iod,app,1) .
#   # eq iodineClient4Addr = a(cl[4],hcs,iod,cl,1) .
#   # eq iodineClient4NetClientAddr = a(cl[4],tcp,iod,cl,1) 

#   # eq ircClient4          = mkIrcClient-v2(ircClient4Addr, client4IfaceAddr, "Client4") .
#   # eq ircClient4UserModel = mkIrcUMV2Actor(ircClient4UserModelAddr, "irc-test", ircClient4Addr) .
#   # eq client4Iface        = mkIrcByteSeqIface(client4IfaceAddr, ircClient4Addr, sendApp4Addr) .
#   # eq sendApp4            = mkSendApp(sendApp4Addr, rcvApp4Addr, client4IfaceAddr, iodineClient4Addr) .
#   # eq iodineClient4       = makeWClient(iodineClient4Addr, serverIodineServer4Addr, 'pwnd2 . 'com . root, a, 0.0) .
#   # eq iodineClient4NetClient = makeNetClient(iodineClient4NetClientAddr, serverIodineServer4Addr, iodineClient4Addr, true, nullAddr, nullName) .

#   # Create the actual static actors
#   mast_server_iface = Node(
#     mast_server_iface_addr, 
#     "mast_server_iface", 
#     f"mkIrcByteSeqIface({mast_server_iface_addr.name}, {irc_server.addr.name}, {mast_cmas_addr.name})")
#   mast_umas = Node(
#     mast_umas_addr,
#     "mast_umas",
#     f"mkUMactor({mast_umas_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmas_addr.name})")
#   mast_cmas = Node(
#     mast_cmas_addr,
#     "mast_cmas",
#     f'mkCMSndRcvActor({mast_cmas_addr.name}, {mast_edas_addr.name}, {mast_mcas_addr.name}, {mast_server_iface_addr.name}, "server5", "client5")')
#   mast_mcas = Node(
#     mast_mcas_addr,
#     "mast_mcas",
#     f"makeMastodonClient({mast_mcas_addr.name}, {mast_subnet_router_addr.name}, {mast_cmas_addr.name})")
#   mast_edas = Node(
#     mast_edas_addr,
#     "mast_edas",
#     f"makeDestiniActor({mast_edas_addr.name}, ed-iamges)")
#   mast_server = Node(
#     mast_server_addr,
#     "mast_server",
#     f"makeNetServer({mast_server_addr.name}, {mast_subnet_router_addr.name})")
#   mast_server_netclient = Node(
#     mast_server_netclient_addr,
#     "mast_server_netclient",
#     f"makeNetClient({mast_server_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcas_addr.name}, true, nullAddr, nullName)")
#   mast_subnet_router = Node(
#     mast_subnet_router_addr,
#     "mast_subnet_router",
#     f"makeMastodonServer({mast_subnet_router_addr.name})")

#   nodes += [mast_server_iface, mast_umas, mast_cmas, mast_mcas, mast_edas, mast_server, mast_server_netclient, mast_subnet_router]

#   hcs_config = yml_nodes["node_type_mastodon"]
#   num_hcs_clients = hcs_config["client_per_network"]["client_net_mastodon"]["quantity"]

#   client_nodes: dict[str, Node] = {}
#   client_addrs: list[Address] = []

#   for i in range(num_hcs_clients):
#     mast_client_addr = Address(f"mast_client_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,cl,{i})")
#     mast_client_user_model_addr = Address(f"mast_client_user_model_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,um,{i})")
#     mast_client_iface_addr = Address(f"mast_client_iface_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,if,{i})")
#     mast_umac_addr = Address(f"mast_umac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,um,{i})")
#     mast_cmac_addr = Address(f"mast_cmac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,cm,{i})")
#     mast_mcac_addr = Address(f"mast_mcac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,mc,{i})")
#     mast_edac_addr = Address(f"mast_edac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,ed,{i})")
#     mast_client_netclient_addr = Address(f"mast_client_netclient_addr_{i}", f"a(cl[{subnet_idx}],tcp,mas,cl,{i})")
#     client_addrs.append(mast_client_addr)

#     named_nodes = {
#       f"mast_client_{i}": Node(
#         mast_client_addr, 
#         f"mast_client_{i}", 
#         f'mkIrcClient-v2({mast_client_addr.name}, {mast_client_iface_addr.name}, "Client{subnet_idx}")'),
      
#       f"mast_client_user_model_{i}": Node(
#         mast_client_user_model_addr, 
#         f"mast_client_user_model_{i}", 
#         f'mkIrcUMV2Actor({mast_client_user_model_addr.name}, "irc-test", {mast_client_addr.name})'),

#       f"mast_client_iface_{i}": Node(
#         mast_client_iface_addr, 
#         f"mast_client_iface_{i}", 
#         f"mkIrcByteSeqIface({mast_client_iface_addr.name}, {mast_client_addr.name}, {mast_cmac_addr.name})"),

#       f"mast_umac_{i}": Node(
#         mast_umac_addr, 
#         f"mast_umac_{i}", 
#         f"mkUMactor({mast_umac_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmac_addr.name})"),

#       f"mast_cmac_{i}": Node(
#         mast_cmac_addr, 
#         f"mast_cmac_{i}", 
#         f'mkCMSndRcvActor({mast_cmac_addr.name}, {mast_edac_addr.name}, {mast_mcac_addr.name}, {mast_client_iface_addr.name}, "mast_client_{i}", "mast_server")'),

#       f"mast_mcac_{i}": Node(
#         mast_mcac_addr, 
#         f"mast_mcac_{i}", 
#         f"makeMastodonClient({mast_mcac_addr.name}, {mast_subnet_router_addr.name}, {mast_cmac_addr.name})"),

#       f"mast_edac_{i}": Node(
#         mast_edac_addr, 
#         f"mast_edac_{i}", 
#         f"makeDestiniActor({mast_edac_addr.name}, ed-images)"),

#       f"mast_client_netclient_{i}": Node(
#         mast_client_netclient_addr, 
#         f"mast_client_netclient_{i}", 
#         f"makeNetClient({mast_client_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcac_addr.name}, true, nullAddr, nullName)"),
#     }

#     nodes += named_nodes.values()
#     client_nodes.update(named_nodes)

#   # server_subnet_config = yml_subnets["mastodon_net"]["params"]
  
#   # server_up_latency = server_subnet_config["upstream"]["latency"]
#   # server_down_latency = server_subnet_config["downstream"]["latency"]

#   # server_up_loss = loss_specs[server_subnet_config["upstream"]["loss_profile"]]
#   # server_down_loss = loss_specs[server_subnet_config["downstream"]["loss_profile"]]

#   # TODO: give these the proper linktypes! Ask Christophe exactly how to combine probabilities
#   links = [
#     Link(mast_subnet_router, mast_mcas),
#     Link(mast_mcas, mast_subnet_router),
#     Link(mast_subnet_router, None),
#     Link(None, mast_subnet_router),
#     Link(mast_mcas, None),
#     Link(None, mast_mcas),
#   ]

#   # client_subnet_config = yml_subnets["client_net_mastodon"]["params"]

#   # client_up_latency = client_subnet_config["upstream"]["latency"]
#   # client_down_latency = client_subnet_config["downstream"]["latency"]

#   # client_up_loss = loss_specs[client_subnet_config["upstream"]["loss_profile"]]
#   # client_down_loss = loss_specs[client_subnet_config["downstream"]["loss_profile"]]

#   for i in range(num_hcs_clients):
#     links += [
#       Link(client_nodes[f"mast_mcac_{i}"], None),
#       Link(None, client_nodes[f"mast_mcac_{i}"]),

#       Link(mast_subnet_router, client_nodes[f"mast_mcac_{i}"]),
#       Link(client_nodes[f"mast_mcac_{i}"], mast_subnet_router),
#     ]

#   return (Topology(True, nodes, links), mast_server, client_addrs)









