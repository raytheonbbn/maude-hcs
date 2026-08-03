from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_gorilla_tgen(
    cfg: TGenConfig,
    tgen_idx: int,
    addr_ctr: Counter,
    ixp_linktype: LinkType,
) -> Cp3ConfigChunk:

  addr_decls = Lines(
    f"gor_tgen{tgen_idx}_usermodel_addr",
    f"gor_tgen{tgen_idx}_tgen_addr",
    f"gor_tgen{tgen_idx}_netclient_addr",
  )

  addr_binds = Lines(
    f"--- gorTgen on {cfg.client_subnet_name} #{tgen_idx} (cl[{cfg.client_subnet_idx}], profile={cfg.profile})",
    f"eq gor_tgen{tgen_idx}_usermodel_addr = a(cl[{cfg.client_subnet_idx}], tgen, gor, um, {addr_ctr()}) .",
    f"eq gor_tgen{tgen_idx}_tgen_addr  = a(cl[{cfg.client_subnet_idx}], tgen, gor, cl, {addr_ctr()}) .",
    f"eq gor_tgen{tgen_idx}_netclient_addr = a(cl[{cfg.client_subnet_idx}], tcp, gor, cl, {addr_ctr()}) .",
  )

  transports = Lines(
    f"eq transport(gor_tgen{tgen_idx}_tgen_addr) = tcp(gor_tgen{tgen_idx}_tgen_addr) ."
  )

  linkdata = Lines(
    f"aaa(gor_tgen{tgen_idx}_tgen_addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})",
    f"aaa(IXP-DEFAULT-ADDR, gor_tgen{tgen_idx}_tgen_addr, {ixp_linktype.name()})",
  )

  actor_decls = Lines(
    f"gor_tgen{tgen_idx}_usermodel",
    f"gor_tgen{tgen_idx}_tgen",
    f"gor_tgen{tgen_idx}_netclient",
  )

  actor_binds = Lines(
    f"--- gorTgen on {cfg.client_subnet_name} #{tgen_idx} (cl[{cfg.client_subnet_idx}], profile={cfg.profile})",
    f"eq gor_tgen{tgen_idx}_tgen = mkGorillaChatTgenA(gor_tgen{tgen_idx}_tgen_addr, gorilla-server-addr) .",
    f'eq gor_tgen{tgen_idx}_usermodel  = mkTgenUMV2Actor(gor_tgen{tgen_idx}_usermodel_addr, "{cfg.profile}", gor_tgen{tgen_idx}_tgen_addr) .',
    f"eq gor_tgen{tgen_idx}_netclient = makeNetClient(gor_tgen{tgen_idx}_netclient_addr,",
      f"gorilla-server-addr,",
      f"gor_tgen{tgen_idx}_tgen_addr,",
      f"true,",
      f"{cfg.client_subnet_dns},",
      f"nullName) .",
  )

  init_actors = Lines(
    f"gor_tgen{tgen_idx}_usermodel",
    f"gor_tgen{tgen_idx}_tgen",
    f"gor_tgen{tgen_idx}_netclient",
  )

  init_msgs = Lines(
    f"[tgenDelay + genRandomX(j, 0.0, 0.0001), (to gor_tgen{tgen_idx}_usermodel_addr from gor_tgen{tgen_idx}_usermodel_addr : burstDelayTO), 0]"
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