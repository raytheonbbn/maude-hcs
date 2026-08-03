from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_dns_tgen(
    cfg: TGenConfig,
    tgen_idx: int,
    addr_ctr: Counter,
    ixp_linktype: LinkType,
) -> Cp3ConfigChunk:

  addr_decls = Lines(
    f"dns_tgen{tgen_idx}_usermodel_addr",
    f"dns_tgen{tgen_idx}_tgen_addr",
  )

  addr_binds = Lines(
    f"--- dnsTgen on {cfg.client_subnet_name} #{tgen_idx} (cl[{cfg.client_subnet_idx}], profile={cfg.profile})",
    f"eq dns_tgen{tgen_idx}_usermodel_addr = a(cl[{cfg.client_subnet_idx}], tgen, dns, um, {addr_ctr()}) .",
    f"eq dns_tgen{tgen_idx}_tgen_addr = a(cl[{cfg.client_subnet_idx}], tgen, dns, cl, {addr_ctr()}) .",
  )

  actor_decls = Lines(
    f"dns_tgen{tgen_idx}_usermodel",
    f"dns_tgen{tgen_idx}_tgen",
  )

  actor_binds = Lines(
    f"--- DNS TGEN: (profile={cfg.profile}, network={cfg.client_subnet_name})",
    f"eq dns_tgen{tgen_idx}_tgen = mkDnsTgenA(dns_tgen{tgen_idx}_tgen_addr, corp-mas-dns-addr, 1000, 5.0, 2) .",
    f"eq dns_tgen{tgen_idx}_usermodel = mkUMactor(dns_tgen{tgen_idx}_usermodel_addr, {cfg.profile}, dns_tgen{tgen_idx}_tgen_addr) .",
  )

  init_actors = Lines(
    f"dns_tgen{tgen_idx}_usermodel",
    f"dns_tgen{tgen_idx}_tgen",
  )

  init_msgs = Lines(
    f"[tgenDelay + genRandomX(j, 0.0, 0.0001), (to dns_tgen{tgen_idx}_usermodel_addr from dns_tgen{tgen_idx}_usermodel_addr : burstDelayTO), 0]",
  )

  return Cp3ConfigChunk(
    addr_decls=addr_decls,
    addr_binds=addr_binds,
    actor_decls=actor_decls,
    actor_binds=actor_binds,
    init_actors=init_actors,
    init_msgs=init_msgs
  )