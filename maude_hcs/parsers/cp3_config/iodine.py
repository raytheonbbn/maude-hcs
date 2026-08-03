from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_iodine_hcs_client(
    client_subnet_idx: int,
    iod_subnet_idx: int,
    client_idx: int,
    addr_ctr: Counter,
    subnet_linktypes: tuple[LinkType, LinkType],
    ixp_linktype: LinkType,
    profile: str,
) -> Cp3ConfigChunk:


  # TODO: why the heck does zoneInternetCom get the iodine client 7 stuff? Can't put that here, need to ask about it.
  zones = Lines(
    f"op zonePwndCom{iod_subnet_idx} : -> List{{Record}} .",
    f"eq zonePwndCom{iod_subnet_idx} =",
    "< 'pwnd . 'com . root, soa, 360000.0, soaData(360000.0) >",
    "< 'pwnd . 'com . root, ns, 360000.0, 'ns . 'pwnd . 'com . root >",
    f"< 'ns . 'pwnd . 'com . root, a, 360000.0, iod-server-client{client_idx}-server-addr >",
    "< 'www0 . 'pwnd . 'com . root, a, 360000.0, 2 . 0 . 1 . 2 >",
    "< 'www1 . 'pwnd . 'com . root, a, 360000.0, 2 . 1 . 1 . 2 >",
    "< wildcard . 'pwnd . 'com . root, txt, 360000.0, nullAddr > .",
  )

  # TODO: why is only iodine 7 in here, in the reference config? shouldn't 8 be as well?
  resolver_cache = Lines(
    f"cacheEntry(< 'ns . 't1 . 'pwnd . 'com . root, a, 360000.0, iod-server-client{client_idx}-server-addr >, 1)"
  )

  addr_pairs = [
    Insert(InsertType.DECL, Lines(f"--- Iodine Client {client_idx} (Network cl[{client_subnet_idx}])")),
    (f"iod-client{client_idx}-irc-addr", f"a(cl[{client_subnet_idx}], hcs, irc, cl, {addr_ctr()})"),
    (f"iod-client{client_idx}-usermodel-addr", f"a(cl[{client_subnet_idx}], hcs, irc, um, {addr_ctr()})"),
    (f"iod-client{client_idx}-iface-addr", f"a(cl[{client_subnet_idx}], hcs, irc, if, {addr_ctr()})"),
    (f"iod-client{client_idx}-sendapp-addr", f"a(cl[{client_subnet_idx}], hcs, iod, app, {addr_ctr()})"),
    (f"iod-client{client_idx}-client-addr", f"a(cl[{client_subnet_idx}], hcs, iod, cl, {addr_ctr()})"),

    (f"iod-server-client{client_idx}-rcvapp-addr", f"a(srvN[{iod_subnet_idx}], hcs, iod, app, {addr_ctr()})"),
    (f"iod-server-client{client_idx}-server-addr", f"a(srvN[{iod_subnet_idx}], hcs, iod, iodSrv, {addr_ctr()})"),
    (f"iod-server-client{client_idx}-iface-addr", f"a(srvN[{iod_subnet_idx}], hcs, irc, if, {addr_ctr()})"),
    (f"iod-server-client{client_idx}-netserver-addr", f"a(srvN[{iod_subnet_idx}], tcp, iod, srv, {addr_ctr()})"),
  ]

  addr_decls, addr_binds = pairs_to_names_and_binds(addr_pairs)

  # TODO: corp dns addrs have to be done differently, consult with team
  transports = Lines(
    f"eq transport(corp-iod-dns-addr) = corp-iod-dns-addr .",
    f"eq transport(iod-server-client{client_idx}-server-addr) = iod-server-client{client_idx}-server-addr .",
    f"eq transport(iod-server-client{client_idx}-netserver-addr) = iod-server-client{client_idx}-netserver-addr .",
  )

  linkdata = Lines(
    f'aaa(iod-server-client{client_idx}-server-addr, iod-client{client_idx}-client-addr, {subnet_linktypes[0].name()})',
    f'aaa(iod-client{client_idx}-client-addr, iod-server-client{client_idx}-server-addr, {subnet_linktypes[0].name()})',
    f'aaa(corp-iod-dns-addr, public-dns-addr, {subnet_linktypes[0].name()})',
    f'aaa(public-dns-addr, corp-iod-dns-addr, {subnet_linktypes[0].name()})',
    f'aaa(iod-server-client{client_idx}-server-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})',
    f'aaa(IXP-DEFAULT-ADDR, iod-server-client{client_idx}-server-addr, {ixp_linktype.name()})',
    f'aaa(iod-client{client_idx}-client-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})',
    f'aaa(IXP-DEFAULT-ADDR, iod-client{client_idx}-client-addr, {ixp_linktype.name()})',
  )

  actor_pairs = [
    Insert(InsertType.DECL, Lines(f"--- Iodine Client {client_idx} (IRC profile: {profile})")),
    (f"iod-client{client_idx}-irc", f'mkIrcClient-v2(iod-client{client_idx}-irc-addr, iod-client{client_idx}-iface-addr, "IodClient{client_idx}")'),
    (f"iod-client{client_idx}-usermodel", f'mkIrcUMV2Actor(iod-client{client_idx}-usermodel-addr, {profile}, iod-client{client_idx}-irc-addr)'),
    (f"iod-client{client_idx}-iface", f'mkIrcByteSeqIface(iod-client{client_idx}-iface-addr, iod-client{client_idx}-irc-addr, iod-client{client_idx}-sendapp-addr)'),
    (f"iod-client{client_idx}-sendapp", f'mkSendApp(iod-client{client_idx}-sendapp-addr, iod-server-client{client_idx}-rcvapp-addr, iod-client{client_idx}-iface-addr, iod-client{client_idx}-client-addr)'),
    (f"iod-client{client_idx}-client", f"makeWClient(iod-client{client_idx}-client-addr, corp-iod-dns-addr, 't1 . 'pwnd . 'com . root, a, 0.0)"),

    (f"iod-server-client{client_idx}-rcvapp", f'mkRcvApp(iod-server-client{client_idx}-rcvapp-addr, iod-client{client_idx}-sendapp-addr, iod-server-client{client_idx}-iface-addr, iod-server-client{client_idx}-server-addr)'),
    (f"iod-server-client{client_idx}-server", f'makeWNameServer(iod-server-client{client_idx}-server-addr, 0.0, zonePwndCom{client_idx})'),
    (f"iod-server-client{client_idx}-iface", f'mkIrcByteSeqIface(iod-server-client{client_idx}-iface-addr, irc-server-addr, iod-server-client{client_idx}-rcvapp-addr)'),
  ]

  iod_netserver = Lines(
    f"makeNetClient(iod-server-client{client_idx}-netserver-addr,",
    indented_lines(
      f"public-dns-addr,",
      f"iod-server-client{client_idx}-server-addr,",
      f"true,",
      f"nullAddr,",
      f"nullName) .",
    ),
  )
  actor_pairs.append((f"iod-server-client{client_idx}-netserver", iod_netserver))
  actor_decls, actor_binds = pairs_to_names_and_binds(actor_pairs)

  init_actors = Lines(
    f"iod-client{client_idx}-irc",
    f"iod-client{client_idx}-usermodel",
    f"iod-client{client_idx}-iface",
    f"iod-client{client_idx}-sendapp", 
    f"iod-client{client_idx}-client",

    f"iod-server-client{client_idx}-rcvapp",
    f"iod-server-client{client_idx}-server",
    f"iod-server-client{client_idx}-iface",
    f"iod-server-client{client_idx}-netserver",
  )

  init_msgs = Lines(
    f"[hcsDelay + 10.0 + genRandomX(j, 0.0, 0.0001), (to iod-client{client_idx}-usermodel-addr from iod-client{client_idx}-usermodel-addr : burstDelayTO), 0]"
  )

  return Cp3ConfigChunk(
    zones=zones,
    resolver_cache=resolver_cache,

    addr_binds=addr_binds,
    transports=transports,
    linkdata=linkdata,
    actor_decls=actor_decls,
    actor_binds=actor_binds,
    init_actors=init_actors,
    init_msgs=init_msgs
  )