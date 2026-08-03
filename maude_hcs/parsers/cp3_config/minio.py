from .common import Lines, indented_lines, LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, profile_to_maude, Insert, InsertType, pairs_to_names_and_binds

def mk_minio_tgen(
    cfg: TGenConfig,
    tgen_idx: int,
    addr_ctr: Counter,
    ixp_linktype: LinkType,
) -> Cp3ConfigChunk:

  addr_decls = Lines(
    f"min-tgen{tgen_idx}-usermodel-addr",
    f"min-tgen{tgen_idx}-tgen-addr",
    f"min-tgen{tgen_idx}-s3-client-addr",
    f"min-tgen{tgen_idx}-netclient-addr",
  )

  addr_binds = Lines(
    f"eq min-tgen{tgen_idx}-usermodel-addr = a(cl[{cfg.client_subnet_dns}], tgen, min, um, {addr_ctr()}) .",
    f"eq min-tgen{tgen_idx}-tgen-addr = a(cl[{cfg.client_subnet_dns}], tgen, min, cl, {addr_ctr()}) .",
    f"eq min-tgen{tgen_idx}-s3-client-addr = a(cl[{cfg.client_subnet_dns}], tgen, min, if, {addr_ctr()}) .",
    f"eq min-tgen{tgen_idx}-netclient-addr = a(cl[{cfg.client_subnet_dns}], tcp, min, cl, {addr_ctr()}) .",
  )

  transports = Lines(
    f"eq transport(min-tgen{tgen_idx}-tgen-addr) = tcp(min-tgen{tgen_idx}-tgen-addr) .",
    f"eq transport(min-tgen{tgen_idx}-s3-client-addr) = tcp(min-tgen{tgen_idx}-s3-client-addr) .",
  )

  linkdata = Lines(
    f"aaa(min-tgen{tgen_idx}-s3-client-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})",
    f"aaa(IXP-DEFAULT-ADDR, min-tgen{tgen_idx}-s3-client-addr, {ixp_linktype.name()})",
    f"aaa(min-tgen{tgen_idx}-tgen-addr, IXP-DEFAULT-ADDR, {ixp_linktype.name()})",
    f"aaa(IXP-DEFAULT-ADDR, min-tgen{tgen_idx}-tgen-addr, {ixp_linktype.name()})",
  )

  actor_decls = Lines(
    f"min-tgen{tgen_idx}-usermodel",
    f"min-tgen{tgen_idx}-tgen",
    f"min-tgen{tgen_idx}-s3-client",
    f"min-tgen{tgen_idx}-netclient",
  )

  actor_binds = Lines(
    # f'--- MinIO TGEN: minTgenMas1 (profile=fast, network=client_net_mastodon)',
    f'ops minTgenMas1Act minTgenMas1UmAct minTgenMas1S3ClAct minTgenMas1NetClAct : -> Actor .',
    f'eq min-tgen{tgen_idx}-tgen = mkMinioTgenA(min-tgen{tgen_idx}-tgen-addr, min-tgen{tgen_idx}-s3-client-addr, "tgen", "minio") .',
    f'eq minTgenMas1S3ClAct = makeS3Client(min-tgen{tgen_idx}-s3-client-addr, minio-s3-server-addr) .',
    f'eq min-tgen{tgen_idx}-usermodel  = mkTgenUMV2Actor(min-tgen{tgen_idx}-usermodel-addr, "{cfg.profile}", min-tgen{tgen_idx}-tgen-addr) .',
    f'eq minTgenMas1NetClAct = makeNetClient(min-tgen{tgen_idx}-s3-client-addr,',
    indented_lines(
      f'minio-s3-server-addr,',
      f'min-tgen{tgen_idx}-s3-client,',
      f'true,',
      f'nullAddr,',
      f'nullName) .',),
  )

  init_actors = actor_decls
  init_msgs = Lines(
    f"[tgenDelay + genRandomX(j, 0.0, 0.0001), (to min-tgen{tgen_idx}-usermodel-addr from min-tgen{tgen_idx}-usermodel-addr : burstDelayTO), 0]"
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

