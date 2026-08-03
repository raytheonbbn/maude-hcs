from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_skyhook_hcs_client(
    client_subnet_idx: int,
    client_idx: int,
    addr_ctr: Counter,
    subnet_linktypes: tuple[LinkType, LinkType],
    ixp_linktype: LinkType,
    profile: str,
) -> Cp3ConfigChunk:
  # TODO: what are skyCl3PuaAddr and skyCl3AhaAddr

  addr_pairs = [
    (f"sky-client{client_idx}-irc-addr", "a(cl[5], hcs, irc, cl, 1)"),
    (f"sky-client{client_idx}-addr", "a(cl[5], hcs, irc, um, 1)"),
    (f"sky-client{client_idx}-iface-addr", "a(cl[5], hcs, irc, if, 1)"),

    (f"sky-client{client_idx}-usermodel-addr", "a(cl[5], hcs, sky, um, 1)"),
    (f"sky-client{client_idx}-cmgr-addr", "a(cl[5], hcs, sky, cm, 1)"),
    (f"skyCl3PuaAddr", ""),
    (f"sky-client{client_idx}-sdk-addr", "a(cl[5], hcs, sky, dl, 1)"),
    (f"sky-client{client_idx}-netclient-addr", "a(cl[5], tcp, sky, cl, 1)"),

    (f"sky-server-client{client_idx}-iface-addr", "a(srvN[3], hcs, irc, if, 1)"),
    (f"sky-server-client{client_idx}-usermodel-addr", "a(srvN[3], hcs, sky, um, 1)"),
    (f"sky-server-client{client_idx}-cmgr-addr", "a(srvN[3], hcs, sky, cm, 1)"),
    (f"skyCl3AhaAddr", ""),
    (f"sky-server-client{client_idx}-sdk-addr", "a(srvN[3], hcs, sky, dl, 1)"),
    (f"sky-server-client{client_idx}-netclient-addr", "a(srvN[3], tcp, sky, cl, 1)"),
    (f"sky-server-client{client_idx}-netserver-addr", "a(srvN[3], tcp, sky, srv, 0)"),
  ]

  # eq skyCl3IrcAddr       = a(cl[5], hcs, irc, cl, 1) .
  # eq skyCl3UmAddr        = a(cl[5], hcs, irc, um, 1) .
  # eq skyCl3IfaceAddr     = a(cl[5], hcs, irc, if, 1) .
  # eq skyCl3SrvIfaceAddr  = a(srvN[3], hcs, irc, if, 1) .
  # eq skyCl3UmacAddr      = a(cl[5], hcs, sky, um, 1) .
  # eq skyCl3CmacAddr      = a(cl[5], hcs, sky, cm, 1) .
  # eq skyCl3PuaAddr       = a(cl[5], hcs, sky, pu, 1) .
  # eq skyCl3SdkacAddr     = a(cl[5], hcs, sky, dl, 1) .
  # eq skyCl3UmasAddr      = a(srvN[3], hcs, sky, um, 1) .
  # eq skyCl3CmasAddr      = a(srvN[3], hcs, sky, cm, 1) .
  # eq skyCl3AhaAddr       = a(srvN[3], hcs, sky, ah, 1) .
  # eq skyCl3SdkasAddr     = a(srvN[3], hcs, sky, dl, 1) .
  # eq skyCl3ClNetAddr     = a(cl[5], tcp, sky, cl, 1) .
  # eq skyCl3SrvNetClAddr  = a(srvN[3], tcp, sky, cl, 1) .
  # eq skyCl3NetSrvAddr    = a(srvN[3], tcp, sky, srv, 0) .

  addr_decls, addr_binds = pairs_to_names_and_binds(addr_pairs)

  transports = Lines(
    f"eq transport(sky-client{client_idx}-sdk-addr) = tcp(sky-client{client_idx}-sdk-addr) .",
    f"eq transport(sky-server-client{client_idx}-sdk-addr) = tcp(sky-server-client{client_idx}-sdk-addr) .",
  )

  linkdata = Lines(
    f'aaa(s3-server-addr, sky-client{client_idx}-sdk-addr, LinkType-ClientNetSky)',
    f'aaa(sky-client{client_idx}-sdk-addr, s3-server-addr, LinkType-ClientNetSky)',
    f'aaa(s3-server-addr, sky-server-client{client_idx}-sdk-addr, LinkType-ClientNetSky)',
    f'aaa(sky-server-client{client_idx}-sdk-addr, s3-server-addr, LinkType-ClientNetSky)',
    f'aaa(sky-client{client_idx}-sdk-addr, IXP-DEFAULT-ADDR, LinkType-Ixp)',
    f'aaa(IXP-DEFAULT-ADDR, sky-client{client_idx}-sdk-addr, LinkType-Ixp)',
    f'aaa(sky-server-client{client_idx}-sdk-addr, IXP-DEFAULT-ADDR, LinkType-Ixp)',
    f'aaa(IXP-DEFAULT-ADDR, sky-server-client{client_idx}-sdk-addr, LinkType-Ixp)',
  )

  actor_pairs = [
    (f"sky-client{client_idx}-irc", f'mkIrcClient-v2(sky-client{client_idx}-irc-addr, sky-client{client_idx}-iface-addr, "SkyClient3")'),
    (f"sky-client{client_idx}-usermodel", f'mkIrcUMV2Actor(sky-client{client_idx}-addr, "irc-irc-3", sky-client{client_idx}-irc-addr)'),
    (f"sky-client{client_idx}-iface", f'mkIrcByteSeqIface(sky-client{client_idx}-iface-addr, sky-client{client_idx}-irc-addr, skyCl3CmacAddr)'),

    (f"sky-client{client_idx}-usermodel", f'mkUMactor(sky-client{client_idx}-usermodel-addr skyhook-um-mamodel-1-ma, skyCl3CmacAddr)'),
    (f"sky-client{client_idx}-cmgr", f'mkCMSimpleBi(sky-client{client_idx}-cmgr-addr, sky-client{client_idx}-iface-addr, skyCl3PuaAddr)'),
    (f"skyCl3PuaAddr", ""),
    (f"sky-client{client_idx}-sdk", f'makeS3Client(sky-client{client_idx}-sdk-addr, s3-server-addr)'),

    (f"sky-server-client{client_idx}-iface", f'mkIrcByteSeqIface(sky-server-client{client_idx}-iface-addr, irc-server-addr, sky-server-client{client_idx}-cmgr-addr)'),
    (f"sky-server-client{client_idx}-usermodel", f'mkUMactor(skyCl3UmasAddr, skyhook-um-mamodel-1-ma, sky-server-client{client_idx}-cmgr-addr)'),
    (f"sky-server-client{client_idx}-cmgr", f'mkCMSimpleBi(sky-server-client{client_idx}-cmgr-addr, sky-server-client{client_idx}-iface-addr, skyCl3AhaAddr)'),
    (f"skyCl3AhaAddr", ""),
    (f"sky-server-client{client_idx}-sdk", f'makeS3Client(sky-server-client{client_idx}-sdk-addr, s3-server-addr)'),

    (f"sky-server-client{client_idx}-netserver", f'makeNetServer(sky-server-client{client_idx}-netserver-addr, s3-server-addr)'),
  ]

  sky_client_netclient = Lines(
    f'makeNetClient(sky-client{client_idx}-netclient-addr,'
      f's3-server-addr,'
      f'skyCl3SdkacAddr,'
      f'true,'
      f'corpSkyDnsAddr,'
      f"'mastodon . 'pwnd . 'com . root)"
  )

  sky_server_client_netclient = Lines(
    f'makeNetClient(sky-server-client{client_idx}-netclient-addr,'
      f's3-server-addr,'
      f'sky-server-client{client_idx}-sdk-addr,'
      f'true,'
      f'servDnsAddr,'
      f'nullName)'
  )

  actor_pairs += [(f"sky-client{client_idx}-netclient-addr", sky_client_netclient), (f"sky-server-client{client_idx}-netclient-addr", sky_server_client_netclient)]
  actor_decls, actor_binds = pairs_to_names_and_binds(actor_pairs)

  # eq skyCl3Irc       = 
  # eq skyCl3Um        = 
  # eq skyCl3Iface     = 
  # eq skyCl3UmacAct   = 
  # eq skyCl3CmacAct   = 
  # eq skyCl3PuaAct    = 'makeSkyhookPU(skyCl3PuaAddr, skyCl3CmacAddr, skyCl3SdkacAddr, "s_to_c_bucket_3", "c_to_s_bucket_3", "s_to_c_uuid_3", "c_to_s_uuid_3-hash")'
  # eq skyCl3SdkacAct  = 
  # eq skyCl3SrvIface  = 
  # eq skyCl3UmasAct   = 
  # eq skyCl3CmasAct   = 
  # eq skyCl3AhaAct    = 'mkSkyhookAH(skyCl3AhaAddr, skyCl3CmasAddr, skyCl3SdkasAddr, "c_to_s_bucket_3", "s_to_c_bucket_3", "c_to_s_uuid_3", "s_to_c_uuid_3", "s_to_c_uuid_3", 6)'
  # eq skyCl3SdkasAct  =  .'
  # eq skyCl3ClNet     = 
  # eq skyCl3NetSrv    = 
  # eq skyCl3SrvNetCl  = 

  init_actors = actor_decls
    # --- Skyhook Client 3
    # skyCl3Irc skyCl3Um skyCl3Iface skyCl3UmacAct skyCl3CmacAct skyCl3PuaAct skyCl3SdkacAct
    # skyCl3SrvIface skyCl3UmasAct skyCl3CmasAct skyCl3AhaAct skyCl3SdkasAct
    # skyCl3ClNet skyCl3NetSrv skyCl3SrvNetCl

  init_msgs = Lines(
  f'[hcsDelay + 1.0 + genRandomX(j, 0.0, 0.0001), (to sky-client{client_idx}-usermodel from sky-client{client_idx}-usermodel : actionR("ok")), 0]',
  f'[hcsDelay + 1.0 + genRandomX(s s j, 0.0, 0.0001), (to sky-server-client{client_idx}-usermodel from sky-server-client{client_idx}-usermodel : actionR("ok")), 0]',
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