from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_obfs_hcs_client(
    client_subnet_idx: int,
    client_idx: int,
    addr_ctr: Counter,
    subnet_linktypes: tuple[LinkType, LinkType],
    ixp_linktype: LinkType,
    profile: str,
) -> Cp3ConfigChunk:
  
  addr_pairs = [
    (f"obfs-client{client_idx}-irc-addr", f"a(cl[{client_subnet_idx}], hcs, irc, cl, {client_idx})"),
    (f"obfs-client{client_idx}-um-addr", f"a(cl[{client_subnet_idx}], hcs, irc, um, {client_idx})"),
    (f"obfs-client{client_idx}-iface-addr", f"a(cl[{client_subnet_idx}], hcs, irc, if, {client_idx})"),
    (f"obfs-server-client{client_idx}-iface-addr", f"a(srvN[5], hcs, irc, if, {client_idx})"),
    (f"obfs-client{client_idx}-client-addr", f"a(cl[{client_subnet_idx}], hcs, obfs, cl, {client_idx})"),
    (f"obfs-server-client{client_idx}-server-addr", f"a(srvN[5], hcs, obfs, srv, {client_idx})"),
    (f"obfs-client{client_idx}-netclient-addr", f"a(cl[{client_subnet_idx}], tcp, obfs, cl, {client_idx})"),
    (f"obfs-server-client{client_idx}-netserver-addr", f"a(srvN[5], tcp, obfs, srv, {client_idx})"),
  ]

  addr_decls, addr_binds = pairs_to_names_and_binds(addr_pairs)

  transports = Lines(
    f"eq transport(obfs-client{client_idx}-client-addr) = tcp(obfs-client{client_idx}-client-addr) .",
    f"eq transport(obfs-server-client{client_idx}-server-addr) = tcp(obfs-server-client{client_idx}-server-addr) .",
  )

  linkdata = Lines(
    f"aaa(obfs-client{client_idx}-client-addr, obfs-server-client{client_idx}-server-addr, LinkType-ClientNetObfs)",
    f"aaa(obfs-server-client{client_idx}-server-addr, obfs-client{client_idx}-client-addr, LinkType-ClientNetObfs)",
    f"aaa(obfs-client{client_idx}-client-addr, IXP-DEFAULT-ADDR, LinkType-Ixp)",
    f"aaa(IXP-DEFAULT-ADDR, obfs-client{client_idx}-client-addr, LinkType-Ixp)",
    f"aaa(obfs-server-client{client_idx}-server-addr, IXP-DEFAULT-ADDR, LinkType-Ixp)",
    f"aaa(IXP-DEFAULT-ADDR, obfs-server-client{client_idx}-server-addr, LinkType-Ixp)",
  )

  actor_pairs = [
    (f"obfs-client{client_idx}-irc", f'mkIrcClient-v2(obfs-client{client_idx}-irc-addr, obfs-client{client_idx}-iface-addr, "ObfsClient{client_idx}")'),
    (f"obfs-client{client_idx}-um", f'mkIrcUMV2Actor(obfs-client{client_idx}-um-addr, "{profile}", obfs-client{client_idx}-irc-addr)'),
    (f"obfs-client{client_idx}-iface", f'mkIrcByteSeqIface(obfs-client{client_idx}-iface-addr, obfs-client{client_idx}-irc-addr, obfs-client{client_idx}-client-addr)'),
    (f"obfs-client{client_idx}-cl", f'makeObfs4Node(obfs-client{client_idx}-client-addr, obfs-client{client_idx}-iface-addr, obfs-server-client{client_idx}-server-addr)'),
    (f"obfs-server-client{client_idx}-iface", f'mkIrcByteSeqIface(obfs-server-client{client_idx}-iface-addr, ircServerAddr, obfs-server-client{client_idx}-server-addr)'),
    (f"obfs-server-client{client_idx}-srv", f'makeObfs4Node(obfs-server-client{client_idx}-server-addr, obfs-server-client{client_idx}-iface-addr, obfs-client{client_idx}-client-addr)'),
    (f"obfs-client{client_idx}-netcl", 
     f"makeNetClient(obfs-client{client_idx}-netclient-addr, obfs-server-client{client_idx}-server-addr, obfs-client{client_idx}-client-addr, true, corpObfsDnsAddr, 'mastodon . 'pwnd . 'com . root)"),
    (f"obfs-server-client{client_idx}-netsrv", f'makeNetServer(obfs-server-client{client_idx}-netserver-addr, obfs-server-client{client_idx}-server-addr)'),
  ]

  actor_decls, actor_binds = pairs_to_names_and_binds(actor_pairs)

  init_actors = Lines(
    f"obfs-client{client_idx}-irc obfs-client{client_idx}-um obfs-client{client_idx}-iface obfs-server-client{client_idx}-iface "
    f"obfs-client{client_idx}-cl obfs-server-client{client_idx}-srv obfs-client{client_idx}-netcl obfs-server-client{client_idx}-netsrv"
  )

  init_msgs = Lines(
    f"[hcsDelay + 10.0 + genRandomX(j, 0.0, 0.0001), (to obfs-client{client_idx}-um-addr from obfs-client{client_idx}-um-addr : burstDelayTO), 0]"
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