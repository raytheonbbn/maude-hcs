from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_irc_tgen(
    cfg: TGenConfig,
    tgen_idx: int,
    addr_ctr: Counter,
    ixp_linktype: LinkType,
) -> Cp3ConfigChunk:

  addr_decls = Lines(
    f"irc_tgen{tgen_idx}_usermodel_addr",
    f"irc_tgen{tgen_idx}_tgen_addr",
    f"irc_tgen{tgen_idx}_netclient_addr"
  )

  addr_binds = Lines(
    f"eq irc_tgen{tgen_idx}_usermodel_addr = a(cl[{cfg.client_subnet_idx}], tgen, irc, um, {addr_ctr()}) .",
    f"eq irc_tgen{tgen_idx}_tgen_addr = a(cl[{cfg.client_subnet_idx}], tgen, irc, cl, {addr_ctr()}) .",
    f"eq irc_tgen{tgen_idx}_netclient_addr = a(cl[{cfg.client_subnet_idx}], tcp, irc, cl, {addr_ctr()}) ."
  )

  transports = Lines(
    f"eq transport(irc_tgen{tgen_idx}_tgen_addr) = tcp(irc_tgen{tgen_idx}_tgen_addr) ."
  )

  linkdata = Lines(
    f"aaa(irc_tgen{tgen_idx}_tgen_addr, IXP-DEFAULT-ADDR, LinkType-Ixp)",
    f"aaa(IXP-DEFAULT-ADDR, irc_tgen{tgen_idx}_tgen_addr, LinkType-Ixp)",
  )

  actor_decls = Lines(
    f"irc_tgen{tgen_idx}_usermodel",
    f"irc_tgen{tgen_idx}_tgen",
    f"irc_tgen{tgen_idx}_netclient"
  )

  actor_binds = Lines(
    f'eq irc_tgen{tgen_idx}_usermodel  = mkIrcTgenClient(irc_tgen{tgen_idx}_tgen_addr, irc-server-addr, "ircTgenMas{tgen_idx}") .',
    f'eq irc_tgen{tgen_idx}_tgen = mkIrcUMV2Actor(irc_tgen{tgen_idx}_usermodel_addr, "{cfg.profile}", irc_tgen{tgen_idx}_tgen_addr) .',
    f"eq irc_tgen{tgen_idx}_netclient = makeNetClient(irc_tgen{tgen_idx}_netclient_addr,",
    indented_lines(
      f"irc-server-addr,",
      f"ircTgenMas1TgAddr,",
      f"true,",
      f"nullAddr,",
      f"nullName) .",),
  )

  init_actors = actor_decls
  init_msgs = Lines(
    f"[tgenDelay + genRandomX(j, 0.0, 0.0001), (to irc_tgen{tgen_idx}_usermodel from irc_tgen{tgen_idx}_usermodel : burstDelayTO), 0]"
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
