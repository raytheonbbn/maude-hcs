#!/usr/bin/env python
# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# Maude-HCS Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# The computer software and computer software documentation are licensed
# under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. A copy of the License
# is provided in the LICENSE file, but you may obtain a copy of the
# License at:  https://www.apache.org/licenses/LICENSE-2.0
#
# The computer software and computer software documentation are based
# upon work supported by the Defense Advanced Research Projects Agency (DARPA)
# under Agreement No. HR00l 12590083.
#
# This document does not contain technology or technical data controlled under
# either the U.S. International Traffic in Arms Regulations or the U.S. Export
# Administration Regulations.
#
# DISTRIBUTION STATEMENT A: Approved for public release; distribution is
# unlimited.
#
# Notice: Markings. Any reproduction of this computer software, computer
# software documentation, or portions thereof must also reproduce the markings
# contained herein. Refer to the provided NOTICE file.
#
# MAUDE_HCS: end

import logging, math, pathlib

from dataclasses import dataclass, field, replace
from dataclasses_json import dataclass_json
from collections.abc import Callable
from enum import auto, Enum
from pathlib import Path
from typing import Any, Dict

from maude_hcs.parsers import load_yaml_to_dict

from .common import LinkType, Counter, TGenType, TGenConfig, Cp3ConfigChunk, indent_all, Lines, indented_lines, profile_to_maude
from .mastodon import mk_mastodon_hcs_client, mk_mastodon_tgen
from .iodine import mk_iodine_hcs_client
from .webtunnel import mk_webtunnel_hcs_client
from .skyhook import mk_skyhook_hcs_client
from .obfs import mk_obfs_hcs_client
from .static import mk_static_chunk, mk_static_sloads, mk_static_includes
from .dns import mk_dns_tgen
from .ftp import mk_ftp_tgen
from .gorilla import mk_gorilla_tgen
from .irc import mk_irc_tgen
from .minio import mk_minio_tgen

logger = logging.getLogger(__name__)

def assign_subnet_idxs(yml_subnets: dict) -> dict:
  result = {}
  for i, subnet_name in enumerate(yml_subnets):
    result[subnet_name] = i
  return result

def parse_profile_counts(total: int, profiles: dict[str, float]) -> dict[str, int]:
  """Return the number of tgens that should be assigned to each profile type"""
  result = {}
  current_sum = 0
  prof: str | None = None

  for prof, percent in profiles.items():

    # Formula: ceil(percent * total / 100)
    # Note: 'percent' in yaml is typically 30 for 30%, not 0.3
    count = math.ceil((percent * total) / 100.0)
    result[prof] = count
    current_sum += count
  
  # If we have overshot or undershot, adjust the LAST profile
  # The requirement specifically says "reduce the last section as needed"
  # implying we might have overshot due to ceil()
  if current_sum > total:
    assert prof is not None, "tgen profile dict must be non-empty"
    result[prof] = result[prof] - (current_sum - total)
    assert result[prof] >= 0, "these tgen profile percentages don't make sense!"

  return result

def parse_subnet_linktypes(yml_subnets: dict, linktype_templates: dict[str, LinkType]) -> dict[str, tuple[LinkType, LinkType]]:
  """Return upload/download linktypes for each subnet name in yml_networks"""

  result = {}

  for subnet_name, val in yml_subnets.items():

    params = val["params"]
    print(params)

    up_latency = params["upstream"]["latency"]
    up_profile = params["upstream"]["loss_profile"]
    up_template = linktype_templates[up_profile]
    up_link = replace(up_template, profile=up_profile, latency=up_latency)

    down_latency = params["downstream"]["latency"]
    down_profile = params["downstream"]["loss_profile"]
    down_template = linktype_templates[down_profile]
    down_link = replace(down_template, profile=down_profile, latency=down_latency)

    result[subnet_name] = (up_link, down_link)

  return result

def parse_tgen_cfgs(yml_tgens, subnet_linktypes, subnet_idxs) -> dict[TGenType, list[TGenConfig]]:
  """
  Returned list has one entry for each tgen required. So, in general, the list will contain duplicates, since
  any subnet can contain many tgens with identical characteristics.
  """
  type_map = {
    "tgen_type_mastodon": TGenType.MASTODON,
    "tgen_type_ftp": TGenType.FTP,
    "tgen_type_dns": TGenType.DNS,
    "tgen_type_minio": TGenType.MINIO,
    "tgen_type_gorilla": TGenType.GORILLA,
    "tgen_type_irc": TGenType.IRC,
  }
  result = {}
  for tgen_type_name, val in yml_tgens.items():
    if tgen_type_name not in type_map:
      print(f"Unrecognized tgen type {tgen_type_name}, continuing...")
      continue

    tgen_type = type_map[tgen_type_name]
    tgen_per_network = val["tgen_per_network"]
    result[tgen_type] = []

    for subnet_name, val in tgen_per_network.items():
      linktypes = subnet_linktypes[subnet_name]
      profile_counts = parse_profile_counts(val["quantity"], val["profiles"])

      for profile, count in profile_counts.items():
        tgen_cfg = TGenConfig(profile_to_maude(profile), subnet_name, subnet_idxs[subnet_name], "nullAddr", linktypes[0], linktypes[1])
        result[tgen_type] += [tgen_cfg] * count

  return result

class Cp3Config:
  """Simple class that stores everything we need to generate maude file"""
  # uniq_addrs: dict[str, str]
  # uniq_actors: dict[str, str]

  def __init__(self, yml_path: str, loss_specs_dir: str, baseline_dir: str):

    # 1. Load the raw YAML
    yml = load_yaml_to_dict(Path(yml_path))

    # 1.2 Parse loss specs
    # I |Ii
    # II|I_
    linktype_profiles = ["bad", "poor", "fair", "good", "excellent", "none"]
    linktype_templates = {}
    for ln in linktype_profiles:
        loss_spec_path = Path(loss_specs_dir) / (ln + ".yaml")
        loss_spec = load_yaml_to_dict(loss_spec_path)

        # these are basically "progenitor" or "template" linktypes, since they don't have names or latencies yet
        linktype_templates[ln] = LinkType.from_yml("TEMPLATE_SHOULD_NOT_APPEAR", loss_spec)

    subnet_linktypes = parse_subnet_linktypes(yml["network"], linktype_templates)
    subnet_idxs = assign_subnet_idxs(yml["network"])
    tgen_cfgs = parse_tgen_cfgs(yml["tgen"], subnet_linktypes, subnet_idxs)

    # TODO: why is there a separate ixp linktype? what does it signify?
    # In general, what have we decided with regard to linktypes?
    # The reference config seems to think that up/down linktypes are always the same...
    addr_ctr = Counter(0)
    ixp_linktype = LinkType("ixp", 0.0, 1.0, 0.0, 0.0, 0.0, 0.005)
    chunk_so_far: Cp3ConfigChunk = mk_static_chunk(addr_ctr, ixp_linktype)

    all_linktypes = {ixp_linktype}
    for ltyp0, ltyp1 in subnet_linktypes.values():
      all_linktypes.add(ltyp0)
      all_linktypes.add(ltyp1)

    for cfgs in tgen_cfgs.values():
      for cfg in cfgs:
        all_linktypes.add(cfg.uplink)
        all_linktypes.add(cfg.downlink)

    linktype_decls = Lines(
      *map(lambda x: x.name(), all_linktypes)
    )

    linktype_binds = Lines(
      *map(lambda x: f"eq {x.name()} = {x.maude()} .", all_linktypes)
    )

    chunk_so_far = chunk_so_far.join(Cp3ConfigChunk(linktype_decls=linktype_decls, linktype_binds=linktype_binds))

    for nodetype, dct in yml["nodes"].items():
      match nodetype:
        case "node_type_racetunnel":
          for subnet_name, subnet_params in dct["client_per_network"].items():
            profiles = parse_profile_counts(subnet_params["quantity"], subnet_params["profiles"])
            client_ctr = Counter(0)

            for prof, count in profiles.items():
              profile = profile_to_maude(prof)
              client_subnet_idx = subnet_idxs[subnet_name]
              subnet_linktype = subnet_linktypes[subnet_name]

              for i in range(count):
                chunk = mk_webtunnel_hcs_client(
                  client_subnet_idx,
                  client_ctr(),
                  addr_ctr,
                  subnet_linktype,
                  ixp_linktype,
                  profile
                )
                chunk_so_far = chunk_so_far.join(chunk)
        case "node_type_sky":
          for subnet_name, subnet_params in dct["client_per_network"].items():
            profiles = parse_profile_counts(subnet_params["quantity"], subnet_params["profiles"])
            client_ctr = Counter(0)

            for prof, count in profiles.items():
              profile = profile_to_maude(prof)
              client_subnet_idx = subnet_idxs[subnet_name]
              subnet_linktype = subnet_linktypes[subnet_name]

              for i in range(count):
                chunk = mk_skyhook_hcs_client(
                  client_subnet_idx,
                  client_ctr(),
                  addr_ctr,
                  subnet_linktype,
                  ixp_linktype,
                  profile
                )
                chunk_so_far = chunk_so_far.join(chunk)
        case "node_type_obfs":
          for subnet_name, subnet_params in dct["client_per_network"].items():
            profiles = parse_profile_counts(subnet_params["quantity"], subnet_params["profiles"])
            client_ctr = Counter(0)

            for prof, count in profiles.items():
              profile = profile_to_maude(prof)
              client_subnet_idx = subnet_idxs[subnet_name]
              subnet_linktype = subnet_linktypes[subnet_name]

              for i in range(count):
                chunk = mk_obfs_hcs_client(
                  client_subnet_idx,
                  client_ctr(),
                  addr_ctr,
                  subnet_linktype,
                  ixp_linktype,
                  profile
                )
                chunk_so_far = chunk_so_far.join(chunk)
        case "node_type_iodine":
          for subnet_name, subnet_params in dct["client_per_network"].items():
            profiles = parse_profile_counts(subnet_params["quantity"], subnet_params["profiles"])
            client_ctr = Counter(0)

            for prof, count in profiles.items():
              profile = profile_to_maude(prof)
              client_subnet_idx = subnet_idxs[subnet_name]

              # TODO: where do we actually get iod subnet idx?
              iod_subnet_idx = 0
              subnet_linktype = subnet_linktypes[subnet_name]

              for i in range(count):
                chunk = mk_iodine_hcs_client(
                  client_subnet_idx,
                  iod_subnet_idx,
                  client_ctr(),
                  addr_ctr,
                  subnet_linktype,
                  ixp_linktype,
                  profile
                )
                chunk_so_far = chunk_so_far.join(chunk)

        case "node_type_mastodon":
          for subnet_name, subnet_params in dct["client_per_network"].items():
            profiles = parse_profile_counts(subnet_params["quantity"], subnet_params["profiles"])
            client_ctr = Counter(0)

            for prof, count in profiles.items():
              profile = profile_to_maude(prof)
              client_subnet_idx = subnet_idxs[subnet_name]
              mas_subnet_idx = subnet_idxs["mastodon_net"]
              subnet_linktype = subnet_linktypes[subnet_name]

              for i in range(count):
                chunk = mk_mastodon_hcs_client(
                  client_subnet_idx,
                  client_ctr(),
                  mas_subnet_idx,
                  addr_ctr,
                  subnet_linktype,
                  ixp_linktype,
                  profile
                )
                chunk_so_far = chunk_so_far.join(chunk)

    for typ, cfgs in tgen_cfgs.items():
      match typ:
        case TGenType.IRC:
          for idx, cfg in enumerate(cfgs):
            chunk_so_far = chunk_so_far.join(mk_irc_tgen(cfg, idx, addr_ctr, ixp_linktype))
        case TGenType.MINIO:
          for idx, cfg in enumerate(cfgs):
            chunk_so_far = chunk_so_far.join(mk_minio_tgen(cfg, idx, addr_ctr, ixp_linktype))
        case TGenType.GORILLA:
          for idx, cfg in enumerate(cfgs):
            chunk_so_far = chunk_so_far.join(mk_gorilla_tgen(cfg, idx, addr_ctr, ixp_linktype))
        case TGenType.MASTODON:
          for idx, cfg in enumerate(cfgs):
            chunk_so_far = chunk_so_far.join(mk_mastodon_tgen(cfg, idx, addr_ctr, ixp_linktype))
        case TGenType.FTP:
          for idx, cfg in enumerate(cfgs):
            chunk_so_far = chunk_so_far.join(mk_ftp_tgen(cfg, idx, addr_ctr, ixp_linktype))
        case TGenType.DNS:
          for idx, cfg in enumerate(cfgs):
            chunk_so_far = chunk_so_far.join(mk_dns_tgen(cfg, idx, addr_ctr, ixp_linktype))

    # handle specvial cases (gorilla server, tgen netservers?)
    # Single gorilla server has to be initialized with addresses of all gorilla tgens I think

    # TODO: why do only IRC tgens appear in the client addrs at the end? There are other kidns of tgens.

    self.images = chunk_so_far.images
    self.model_map = chunk_so_far.model_map
    self.zones = chunk_so_far.zones
    self.resolver_caches = chunk_so_far.resolver_cache
    self.addr_decls = chunk_so_far.addr_decls
    self.addr_binds = chunk_so_far.addr_binds
    self.transports = chunk_so_far.transports
    self.linktype_decls = chunk_so_far.linktype_decls
    self.linktype_binds = chunk_so_far.linktype_binds
    self.linkdata = chunk_so_far.linkdata
    self.actor_decls = chunk_so_far.actor_decls
    self.actor_binds = chunk_so_far.actor_binds
    self.init_actors = chunk_so_far.init_actors
    self.init_msgs = chunk_so_far.init_msgs
    self.client_addrs = chunk_so_far.client_addrs

  def to_init_maude(self) -> str:
    lines = Lines(
      '--- MAUDE_HCS: CP3 Scenario 1 Experiment ---',
      '--- Autogenerated from scenario YAML ---',
      '',
      'set clear rules off .',
      'set print attribute off .',
      'set show advisories off .',
      '',
      mk_static_sloads(),
      '',
      'mod HCS_TEST is',
      indented_lines(
        mk_static_includes(),
        'vars j : Nat .',
        '',
        '---------------------------------------------------',
        '--- Global Constants',
        '---------------------------------------------------',
        'eq encOH(fsize:Nat,ksize:Nat) = 0 .',
        'eq noiseMin(msg:Msg)          = 0.00001 .',
        'eq noiseMax(msg:Msg)          = 0.001 .',
        'eq packetSize                 = 1000 .',
        'eq maxPacketSize              = 967 .',
        '--- how much to delay the HCS and TGENs',
        'ops hcsDelay tgenDelay : -> Float .',
        'eq hcsDelay  = 60. [owise] .',
        'eq tgenDelay = 300. [owise] .',
        '',
        '--- User Model Database (MAModelMap)',
        'eq MAModelMap =',
        self.model_map,
        '.',
        'op ed-images : -> ByteSeqL .',
        'eq ed-images =',
          self.images.indent(),
        '.',
        '',
        '---------------------------------------------------',
        '--- DNS Zone Configurations',
        '---------------------------------------------------',
        self.zones,
        'op sb : -> ZoneState .',
        "eq sb = < root ('a . 'root-servers . 'net . root |-> rootDnsAddr) > .",
        '',
        'op resolverCache : -> Cache .',
        'eq resolverCache =',
          self.resolver_caches.indent(),
        '.',
        '---------------------------------------------------',
        '--- HCS Node Addresses',
        '---------------------------------------------------',
        'ops',
          self.addr_decls.indent(),
        ': -> Address .',
        '',
        '---------------------------------------------------',
        '--- Address Equations',
        '---------------------------------------------------',
        self.addr_binds,
        '',
        '---------------------------------------------------',
        '--- Link Model Parameters',
        '---------------------------------------------------',
        'ops',
          self.linktype_decls.indent(),
        ': -> AttributeSet .'
        '',
        self.linktype_binds,
        '',
        '---------------------------------------------------',
        '--- Transport Equations (Readable Addresses Only)',
        '---------------------------------------------------',
        self.transports,
        '',
        '---------------------------------------------------',
        '--- Link Data (Readable Addresses Only)',
        '---------------------------------------------------',
        'eq LinkData =',
          self.linkdata.indent(),
        '.',
        '',
        '---------------------------------------------------',
        '--- Actor Declarations & Definitions',
        '---------------------------------------------------',
        '',
        'ops',
          self.actor_decls.indent(),
        ': -> Actor .',
        '',
        self.actor_binds,
        '',
        '---------------------------------------------------',
        '--- Initial State Configuration',
        '---------------------------------------------------',
        'op initState : Nat -> Config .',
        'eq initState(j) =',
        indented_lines(
          'rCtr(j + 8)',
          '',
          self.init_actors,

          self.init_msgs,),
        '.',
        '',
        '---------------------------------------------------',
        '--- Run Limits and Initial Configuration',
        '---------------------------------------------------',
        '***** suppressing irc server dropping clients',
        'eq IRC-STALE-DURATION-S = 140000. [owise] .',
        'eq IRC-PING-INTV-S = 1200000. [owise]  .',
        '',
        'op slimit : -> Float .',
        'eq slimit = 11700.0 .',
        '',
        'op initConfig : -> Config .',
        'rl[init]: initConfig => run({0.0 | nil} initState(counter), slimit) .',
        '',
        'op allClientsAddr : -> AddrList .',
        'eq allClientsAddr = ',
          self.client_addrs.indent(),
        '',),
      'endm',
      'eof',
      '',
      'set print attribute on .',
      'rew initConfig .',
      'q',
    )
    return '\n'.join(lines.lines)