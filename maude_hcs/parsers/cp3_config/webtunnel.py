from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_webtunnel_hcs_client(
    client_subnet_idx: int,
    client_idx: int,
    addr_ctr: Counter,
    subnet_linktypes: tuple[LinkType, LinkType],
    ixp_linktype: LinkType,
    profile: str,
) -> Cp3ConfigChunk:
  
  addr_pairs = [
    (f"wt-client{client_idx}-irc-addr", f"a(cl[{client_subnet_idx}], hcs, irc, cl, {client_idx})"),
    (f"wt-client{client_idx}-um-addr", f"a(cl[{client_subnet_idx}], hcs, irc, um, {client_idx})"),
    (f"wt-client{client_idx}-iface-addr", f"a(cl[{client_subnet_idx}], hcs, irc, if, {client_idx})"),
    (f"wt-server-client{client_idx}-iface-addr", f"a(srvN[1], hcs, irc, if, {client_idx})"),
    (f"wt-client{client_idx}-client-addr", f"a(cl[{client_subnet_idx}], hcs, wt, cl, {client_idx})"),
    (f"wt-server-client{client_idx}-proxy-addr", f"a(srvN[1], hcs, wt, srv, {client_idx})"),
    (f"wt-client{client_idx}-netclient-addr", f"a(cl[{client_subnet_idx}], tcp, wt, cl, {client_idx})"),
    (f"wt-server-client{client_idx}-netserver-addr", f"a(srvN[1], tcp, wt, srv, {client_idx})"),
  ]

  addr_decls, addr_binds = pairs_to_names_and_binds(addr_pairs)

  transports = Lines(
    f"eq transport(wt-client{client_idx}-client-addr) = tcp(wt-client{client_idx}-client-addr) .",
    f"eq transport(wt-server-client{client_idx}-proxy-addr) = tcp(wt-server-client{client_idx}-proxy-addr) .",
  )

  linkdata = Lines(
    f"aaa(wt-client{client_idx}-client-addr, wt-server-client{client_idx}-proxy-addr, LinkType-ClientNetRacetunnel)",
    f"aaa(wt-server-client{client_idx}-proxy-addr, wt-client{client_idx}-client-addr, LinkType-ClientNetRacetunnel)",
    f"aaa(wt-client{client_idx}-client-addr, IXP-DEFAULT-ADDR, LinkType-Ixp)",
    f"aaa(IXP-DEFAULT-ADDR, wt-client{client_idx}-client-addr, LinkType-Ixp)",
    f"aaa(wt-server-client{client_idx}-proxy-addr, IXP-DEFAULT-ADDR, LinkType-Ixp)",
    f"aaa(IXP-DEFAULT-ADDR, wt-server-client{client_idx}-proxy-addr, LinkType-Ixp)",
  )

  actor_pairs = [
    (f"wt-client{client_idx}-irc", f'mkIrcClient-v2(wt-client{client_idx}-irc-addr, wt-client{client_idx}-iface-addr, "WtClient{client_idx}")'),
    (f"wt-client{client_idx}-um", f'mkIrcUMV2Actor(wt-client{client_idx}-um-addr, "{profile}", wt-client{client_idx}-irc-addr)'),
    (f"wt-client{client_idx}-iface", f'mkIrcByteSeqIface(wt-client{client_idx}-iface-addr, wt-client{client_idx}-irc-addr, wt-client{client_idx}-client-addr)'),
    (f"wt-server-client{client_idx}-iface", f'mkIrcByteSeqIface(wt-server-client{client_idx}-iface-addr, ircServerAddr, wt-server-client{client_idx}-proxy-addr)'),
    (f"wt-client{client_idx}-client", 
     f" < wt-client{client_idx}-client-addr : WtClient |\n"
     f"    thisAddr:        wt-client{client_idx}-client-addr,\n"
     f"    serverProxyAddr: wt-server-client{client_idx}-proxy-addr,\n"
     f"    ircServerAddr:   ircServerAddr,\n"
     f"    ircClientAddr:   wt-client{client_idx}-iface-addr,\n"
     f"    tlsServerName:   \"irc.example.com\",\n"
     f"    upgradePath:     \"secret/path/v1\",\n"
     f"    tunnelState:     Closed,\n"
     f"    pendingMsgs:     emptyQueue >"),
    (f"wt-server-client{client_idx}-proxy", f'makeWtServerProxy(wt-server-client{client_idx}-proxy-addr, wt-server-client{client_idx}-iface-addr)'),
    (f"wt-client{client_idx}-netclient", 
     f"makeNetClient(wt-client{client_idx}-netclient-addr, wt-server-client{client_idx}-proxy-addr, wt-client{client_idx}-client-addr, true, corpRtDnsAddr, 'mastodon . 'pwnd . 'com . root)"),
    (f"wt-server-client{client_idx}-netserver", f'makeNetServer(wt-server-client{client_idx}-netserver-addr, wt-server-client{client_idx}-proxy-addr)'),
  ]

  actor_decls, actor_binds = pairs_to_names_and_binds(actor_pairs)

  init_actors = Lines(
    f"wt-client{client_idx}-irc wt-client{client_idx}-um wt-client{client_idx}-iface wt-server-client{client_idx}-iface "
    f"wt-client{client_idx}-client wt-server-client{client_idx}-proxy wt-client{client_idx}-netclient wt-server-client{client_idx}-netserver"
  )

  init_msgs = Lines(
    f"[hcsDelay + genRandomX(j, 0.0, 0.0001), (to wt-client{client_idx}-client-addr from wt-client{client_idx}-client-addr : WtStartCmd), 0]"
  )

  return Cp3ConfigChunk(
    addr_decls=addr_decls,
    addr_binds=addr_binds,
    transports=transports,
    linkdata=linkdata,
    actor_decls=actor_decls,
    actor_binds=actor_binds,
    init_actors=init_actors,
    init_msgs=init_msgs,
  )