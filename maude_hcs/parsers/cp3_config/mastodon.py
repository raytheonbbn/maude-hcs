from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_mastodon_tgen(
    cfg: TGenConfig,
    tgen_idx: int,
    addr_ctr: Counter,
    ixp_linktype: LinkType,
) -> Cp3ConfigChunk:

  addr_pairs = [
    Insert(InsertType.BIND, Lines(f"--- masTgen on client_net_mastodon #1 (cl[{cfg.client_subnet_idx}], profile={cfg.profile})")),
    (f"mas-tgen{tgen_idx}-usermodel-addr", f"a(cl[{cfg.client_subnet_idx}], tgen, mas, um, {addr_ctr()})"),
    (f"mas-tgen{tgen_idx}-addr", f"a(cl[{cfg.client_subnet_idx}], tgen, mas, cl, {addr_ctr()})"),
    (f"mas-tgen{tgen_idx}-masclient-addr", f"a(cl[{cfg.client_subnet_idx}], tgen, mas, mc, {addr_ctr()})"),
    (f"mas-tgen{tgen_idx}-netclient-addr", f"a(cl[{cfg.client_subnet_idx}], tcp, mas, cl, {addr_ctr()})"),
  ]

  addr_decls, addr_binds = pairs_to_names_and_binds(addr_pairs)

  transports = Lines(
    f"eq transport(mas-tgen{tgen_idx}-masclient-addr) = tcp(mas-tgen{tgen_idx}-masclient-addr)",
    f"eq transport(mas-tgen{tgen_idx}-addr) = tcp(mas-tgen{tgen_idx}-addr)",
  )

  linkdata = Lines(
    f"aaa(mas-tgen{tgen_idx}-masclient-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})",
    f"aaa(IXP-DEFAULT-ADDR, mas-tgen{tgen_idx}-masclient-addr, {ixp_linktype.name()})",
    f"aaa(mas-tgen{tgen_idx}-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})",
    f"aaa(IXP-DEFAULT-ADDR, mas-tgen{tgen_idx}-addr, {ixp_linktype.name()})",
  )

  actor_pairs: list[tuple[str, str | Lines] | Insert] = [
    (f"mas-tgen{tgen_idx}", f"mkMasTGenActor(mas-tgen{tgen_idx}-addr, mas-tgen{tgen_idx}-masclient-addr, ed-images, {cfg.profile})"),
    (f"mas-tgen{tgen_idx}-masclient", f"makeMastodonClient(mas-tgen{tgen_idx}-masclient-addr, mas-server-addr, mas-tgen{tgen_idx}-addr)"),
    (f"mas-tgen{tgen_idx}-usermodel", f"mkUMactor(mas-tgen{tgen_idx}-usermodel-addr, {cfg.profile}, mas-tgen{tgen_idx}-addr)"),
  ]

  mas_tgen_netclient_lines = Lines(
    f"makeNetClient(mas-tgen{tgen_idx}-netclient-addr,",
    indented_lines(
      f"mas-server-addr,",
      f"mas-tgen{tgen_idx}-masclient-addr,",
      f"true,",
      f"{cfg.client_subnet_dns},",
      f"nullName)",),
  )

  actor_pairs.append((f"mas-tgen{tgen_idx}-netclient", mas_tgen_netclient_lines))
  actor_decls, actor_binds = pairs_to_names_and_binds(actor_pairs)

  init_actors = Lines(
    f"mas-tgen{tgen_idx} mas-tgen{tgen_idx}-masclient mas-tgen{tgen_idx}-usermodel mas-tgen{tgen_idx}-netclient"
  )

  init_msgs = Lines(
    f"[tgenDelay + genRandomX(j, 0.0, 0.0001), (to mas-tgen{tgen_idx}-usermodel from mas-tgen{tgen_idx}-usermodel : burstDelayTO), 0]"
  )

  return Cp3ConfigChunk(
    addr_decls=addr_decls,
    addr_binds=addr_binds,
    transports=transports,
    linkdata=linkdata,
    actor_decls=actor_decls,
    actor_binds=actor_binds,
    init_actors=init_actors,
    init_msgs=init_msgs
  )

def mk_mastodon_hcs_client(
    client_subnet_idx: int,
    client_idx: int,
    mas_subnet_idx: int,
    addr_ctr: Counter,
    subnet_linktypes: tuple[LinkType, LinkType],
    ixp_linktype: LinkType,
    profile: str,
) -> Cp3ConfigChunk:

  # TODO:
  # These two lines appear in scenario1_addresses.maude, what the heck is the difference?

  # seems like one is the user model for irc, and the other is user model for mas? alright, fine.
  # Wait, but then why isn't there an irc usermodel on the server side as well?
  #   eq masCl9UmAddr        = a(cl[1], hcs, irc, um, 1) .
  #   eq masCl9UmacAddr      = a(cl[1], hcs, mas, um, 1) .

  #TODO
  # Also, this line:
  # eq masNetSrvAddr         = a(masN, tcp, mas, srv, 0) .
  # Is this static or not? does it belogn to the client or not?
  # It REALLY looks like a netserver for the primary mastodon server, in which case it's static, right?
  # Also, why is it sometimes NetCl, and sometimes ClNet? this is why we need hyphenated names.

  addr_pairs = [
    Insert(InsertType.BIND, Lines("", "--- Why doesn't the server side have an irc usermodel, if it also has a mas usermodel?")),
    (f"mas-client{client_idx}-irc-addr", f"a(cl[{client_subnet_idx}], hcs, irc, cl, {addr_ctr()})"),
    (f"mas-client{client_idx}-irc-usermodel-addr", f"a(cl[{client_subnet_idx}], hcs, irc, um, {addr_ctr()})"),

    Insert(InsertType.BIND, Lines("", "--- When are netclients static, and when are they one-to-one with clients?")),
    (f"mas-client{client_idx}-netclient-addr", f"a(cl[{client_subnet_idx}], tcp, mas, cl, {addr_ctr()})"),
    (f"mas-client{client_idx}-iface-addr", f"a(cl[{client_subnet_idx}], hcs, irc, if, {addr_ctr()})"),
    (f"mas-client{client_idx}-usermodel-addr", f"a(cl[{client_subnet_idx}], hcs, mas, um, {addr_ctr()})"),
    (f"mas-client{client_idx}-cmgr-addr", f"a(cl[{client_subnet_idx}], hcs, mas, cm, {addr_ctr()})"),
    (f"mas-client{client_idx}-masclient-addr", f"a(cl[{client_subnet_idx}], hcs, mas, mc, {addr_ctr()})"),
    (f"mas-client{client_idx}-destini-addr", f"a(cl[{client_subnet_idx}], hcs, mas, ed, {addr_ctr()})"),
    
    Insert(InsertType.BIND, Lines("")),
    (f"mas-server-client{client_idx}-netserver-addr", f"a(srvN[{mas_subnet_idx}], tcp, mas, cl, {addr_ctr()})"),
    (f"mas-server-client{client_idx}-iface-addr", f"a(srvN[{mas_subnet_idx}], hcs, irc, if, {addr_ctr()})"),
    (f"mas-server-client{client_idx}-usermodel-addr", f"a(srvN[{mas_subnet_idx}], hcs, mas, um, {addr_ctr()})"),
    (f"mas-server-client{client_idx}-cmgr-addr", f"a(srvN[{mas_subnet_idx}], hcs, mas, cm, {addr_ctr()})"),
    (f"mas-server-client{client_idx}-masclient-addr", f"a(srvN[{mas_subnet_idx}], hcs, mas, mc, {addr_ctr()})"),
    (f"mas-server-client{client_idx}-destini-addr", f"a(srvN[{mas_subnet_idx}], hcs, mas, ed, {addr_ctr()})"),

    Insert(InsertType.BIND, Lines("", "--- This isn't labeled with a number like the other one-to-one actors. Should this be static? What does it represent?")),
    (f"mas-server-netserver-addr", f"a(masN, tcp, mas, srv, {addr_ctr()})"),
  ]

  addr_decls, addr_binds = pairs_to_names_and_binds(addr_pairs)

  transports = Lines( 
    f"eq transport(mas-client{client_idx}-masclient-addr) = tcp(mas-client{client_idx}-masclient-addr) .",
    f"eq transport(mas-server-client{client_idx}-masclient-addr) = tcp(mas-server-client{client_idx}-masclient-addr) .",
  )

  # OK, let's just assume that linktype;s have been precalculated for us. how do we access them?
  # There's only one linktype we care about here, which is the on from client to mastodon net (and backwards!)
  # TODO: whyb isn't the backwartds one here...
  subnet_linktype = subnet_linktypes[0]

  linkdata = Lines(
    f'aaa(mas-server-addr, mas-client{client_idx}-masclient-addr, {subnet_linktype.name()})',
    f'aaa(mas-client{client_idx}-masclient-addr, mas-server-addr, {subnet_linktype.name()})',
    f'aaa(mas-server-addr, mas-server-client{client_idx}-masclient-addr, {subnet_linktype.name()})',
    f'aaa(mas-server-client{client_idx}-masclient-addr, mas-server-addr, {subnet_linktype.name()})',
    f'aaa(mas-server-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})',
    f'aaa(IXP-DEFAULT-ADDR, mas-server-addr, {ixp_linktype.name()})',
    f'aaa(mas-client{client_idx}-masclient-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})',
    f'aaa(IXP-DEFAULT-ADDR, mas-client{client_idx}-masclient-addr, {ixp_linktype.name()})',
    f'aaa(mas-server-client{client_idx}-masclient-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})',
    f'aaa(IXP-DEFAULT-ADDR, mas-server-client{client_idx}-masclient-addr, {ixp_linktype.name()})',
  )

  actor_pairs = [
    (f"mas-client{client_idx}-irc", f'mkIrcClient-v2(mas-client{client_idx}-irc-addr, mas-client{client_idx}-iface-addr, "MasClient{client_idx}") '),
    (f"mas-client{client_idx}-irc-usermodel", f'mkIrcUMV2Actor(mas-client{client_idx}-usermodel-addr, "{profile}", mas-client{client_idx}-irc-addr)'),

    (f"mas-client{client_idx}-netclient", f"makeNetClient(mas-client{client_idx}-netclient-addr, mas-server-addr, mas-client{client_idx}-masclient-addr, true, corp-mas-dns-addr, 'mastodon . 'pwnd . 'com . root)"),
    (f"mas-client{client_idx}-iface", f'mkIrcByteSeqIface(mas-client{client_idx}-iface-addr, mas-client{client_idx}-irc-addr, mas-client{client_idx}-cmgr-addr)'),
    (f"mas-client{client_idx}-usermodel", f'mkUMactor(mas-client{client_idx}-usermodel-addr, mastodon-client-config-mastodon-bidi-ma, mas-client{client_idx}-cmgr-addr)'),
    (f"mas-client{client_idx}-cmgr", f'mkCMSndRcvActor(mas-client{client_idx}-cmgr-addr, mas-client{client_idx}-destini-addr, mas-client{client_idx}-masclient-addr, mas-client{client_idx}-iface-addr, "client{client_idx}", "server{client_idx}")'),
    (f"mas-client{client_idx}-masclient", f'makeMastodonClient(mas-client{client_idx}-masclient-addr, mas-server-addr, mas-client{client_idx}-cmgr-addr)'),
    (f"mas-client{client_idx}-destini", f'makeDestiniActor(mas-client{client_idx}-destini-addr, ed-images)'),
    
    (f"mas-server-client{client_idx}-netserver", f'makeNetClient(mas-server-client{client_idx}-netserver-addr, mas-server-addr, mas-server-client{client_idx}-masclient-addr, true, serv-dns-addr, nullName)'),
    (f"mas-server-client{client_idx}-iface", f'mkIrcByteSeqIface(mas-server-client{client_idx}-iface-addr, irc-server-addr, mas-server-client{client_idx}-cmgr-addr)'),
    (f"mas-server-client{client_idx}-usermodel", f'mkUMactor(mas-server-client{client_idx}-usermodel-addr, mastodon-server-config-mastodon-bidi-ma, mas-server-client{client_idx}-cmgr-addr)'),
    (f"mas-server-client{client_idx}-cmgr", f'mkCMSndRcvActor(mas-server-client{client_idx}-cmgr-addr, mas-server-client{client_idx}-destini-addr, mas-server-client{client_idx}-masclient-addr, mas-server-client{client_idx}-iface-addr, "server{client_idx}", "client{client_idx}")'),
    (f"mas-server-client{client_idx}-masclient", f'makeMastodonClient(mas-server-client{client_idx}-masclient-addr, mas-server-addr, mas-server-client{client_idx}-cmgr-addr)'),
    (f"mas-server-client{client_idx}-destini", f'makeDestiniActor(mas-server-client{client_idx}-destini-addr, ed-images)'),

    # TODO: is mas-net-server-addr (masNetSrvAddr) static or one-to-one?
    (f"mas-server-netserver", f'makeNetServer(mas-net-server-addr, mas-server-addr)'),
  ]

  actor_decls, actor_binds = pairs_to_names_and_binds(actor_pairs)

  init_actors = Lines(*map(lambda x: x[0], actor_pairs))
  init_msgs = Lines( 
    f'[hcsDelay + 1.0 + genRandomX(j, 0.0, 0.0001), (to mas-client{client_idx}-usermodel from mas-client{client_idx}-usermodel : actionR("ok")), 0]',
    f'[hcsDelay + 1.0 + genRandomX(s s j, 0.0, 0.0001), (to mas-server-client{client_idx}-usermodel from mas-server-client{client_idx}-usermodel : actionR("ok")), 0]',
  )

  client_addrs = Lines( 
    f"mas-client{client_idx}-irc-addr"
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
    client_addrs=client_addrs
  )