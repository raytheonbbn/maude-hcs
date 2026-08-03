from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_ftp_tgen(
    cfg: TGenConfig,
    tgen_idx: int,
    addr_ctr: Counter,
    ixp_linktype: LinkType,
) -> Cp3ConfigChunk:

  addr_decls = Lines(
    f"ftp_tgen{tgen_idx}_usermodel_addr",
    f"ftp_tgen{tgen_idx}_tgen_addr",
    f"ftp_tgen{tgen_idx}_netclient_addr",
  )

  addr_binds = Lines(
    f"--- ftpTgen on {cfg.client_subnet_name} #{tgen_idx} (cl[{cfg.client_subnet_idx}], profile={cfg.profile})",
    f"eq ftp_tgen{tgen_idx}_usermodel_addr = a(cl[{cfg.client_subnet_idx}], tgen, ftp, um, {addr_ctr()}) .",
    f"eq ftp_tgen{tgen_idx}_tgen_addr = a(cl[{cfg.client_subnet_idx}], tgen, ftp, cl, {addr_ctr()}) .",
    f"eq ftp_tgen{tgen_idx}_netclient_addr = a(cl[{cfg.client_subnet_idx}], tcp, ftp, cl, {addr_ctr()}) .",
  )

  transports = Lines(
    f"eq transport(ftp_tgen{tgen_idx}_tgen_addr) = tcp(ftp_tgen{tgen_idx}_tgen_addr) ."
  )

  linkdata = Lines(
    f"aaa(ftp_tgen{tgen_idx}_tgen_addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})",
    f"aaa(IXP-DEFAULT-ADDR, ftp_tgen{tgen_idx}_tgen_addr, {ixp_linktype.name()})",
  )

  actor_decls = Lines(
    f"ftp_tgen{tgen_idx}_usermodel",
    f"ftp_tgen{tgen_idx}_tgen",
    f"ftp_tgen{tgen_idx}_netclient",

  )

  actor_binds = Lines(
    f"--- FTP TGEN: ftp_tgen{tgen_idx} (profile={cfg.profile}, network={cfg.client_subnet_name})",
    f'eq ftp_tgen{tgen_idx}_tgen = mkFtpTgenA(ftp_tgen{tgen_idx}_tgen_addr, ftp-server-addr, 5.0, 2, "{cfg.profile}") .',
    f'eq ftp_tgen{tgen_idx}_usermodel = mkTgenUMV2Actor(ftp_tgen{tgen_idx}_usermodel_addr, "{cfg.profile}", ftp_tgen{tgen_idx}_tgen_addr) .',
    f"eq ftp_tgen{tgen_idx}_netclient = makeNetClient(ftp_tgen{tgen_idx}_netclient_addr,",
      indented_lines(
        f"ftp-server-addr,",
        f"ftp_tgen{tgen_idx}_tgen_addr,",
        f"true,",
        f"{cfg.client_subnet_dns},",
        f"nullName) .",),
  )

  init_actors = Lines(
    f"ftp_tgen{tgen_idx}_usermodel",
    f"ftp_tgen{tgen_idx}_tgen",
    f"ftp_tgen{tgen_idx}_netclient",
  )

  init_msgs = Lines(
    f"[tgenDelay + genRandomX(j, 0.0, 0.0001), (to ftp_tgen{tgen_idx}_usermodel_addr from ftp_tgen{tgen_idx}_usermodel_addr : burstDelayTO), 0]",
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