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

from .common import Address, Node, Link, LinkType, Counter, TGenType, TGenConfig, Topology, indent
from .mastodon import *

# Should be relative to maude_hcs/lib

logger = logging.getLogger(__name__)

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
    up_link = replace(up_template, prof=up_profile, latency=up_latency)

    down_latency = params["downstream"]["latency"]
    down_profile = params["downstream"]["loss_profile"]
    down_template = linktype_templates[down_profile]
    down_link = replace(down_template, prof=down_profile, latency=down_latency)

    result[subnet_name] = (up_link, down_link)

  return result

def parse_tgen_cfgs(yml_tgens, subnet_linktypes) -> dict[TGenType, list[TGenConfig]]:
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

      for prof, count in profile_counts.items():
        tgen_cfg = TGenConfig(prof, linktypes[0], linktypes[1])
        result[tgen_type] += [tgen_cfg] * count

  return result

class Cp3Config:
  """Simple class that stores everything we need to generate maude file"""
  topo: Topology
  undef_addrs: list[str]
  client_addrs: list[Address]

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

    subnet_idx = Counter(0)

    yml_subnets = yml["network"]
    yml_nodes = yml["nodes"]
    yml_tgens = yml["tgen"]

    subnet_linktypes = parse_subnet_linktypes(yml_subnets, linktype_templates)
    tgen_cfgs = parse_tgen_cfgs(yml_tgens, subnet_linktypes)

    irc_server_addr = Address("irc-server-addr", "a(srvN,srv,irc,srv,0)")
    irc_server = Node(irc_server_addr, "irc-server", f"mkIrcServer({irc_server_addr.name})")

    # (racetunnel_topo = mk_racetunnel_topo(networks, nodes, tgen, loss_specs)
    # sky_topo = mk_sky_topo(networks, nodes, tgen, loss_specs)
    # obfs_topo = mk_obfs_topo(networks, nodes, tgen, loss_specs)
    # (iodine_topo, iodine_server_addr, iodine_client_addrs) = mk_iodine_topo(yml_subnets, yml_nodes, linktype_templates, irc_server, subnet_idx())
    (mastodon_topo, mastodon_server, mastodon_client_addrs) = mk_mastodon_topo(yml_subnets, yml_nodes, linktype_templates, irc_server, subnet_idx())
    client_addrs = mastodon_client_addrs

    # Figure this out soon, might be tricky
    # We don't actually care where tgens come from, we just directly connect them to their server.
    # So just figure out how many tgens of each type, and maybe have a function for each type?
    # mastodon_tgens_topo = mk_mastodon_tgens_topo(give all )

    combined_topo = Topology.merge_all([
      # racetunnel_topo,
      # sky_topo,
      # obfs_topo,
      # iodine_topo,
      mastodon_topo
    ])

    combined_topo.nodes.insert(0, irc_server)
    combined_topo.validate()

  # MASTODON = auto()
  # DNS = auto()
  # FTP = auto()
  # MINIO = auto()
  # GORILLA = auto()
  # IRC = auto()

    insert_mastodon_tgens(
      tgen_cfgs[TGenType.MASTODON],
      combined_topo,
      mastodon_server,
      subnet_linktypes["mastodon_net"],
      subnet_idx())

    combined_topo.nodes.append(
      Node(
        Address("iod-server-addr", "a(srvN[4], hcs, iod, iodSrv, 1)"),
        "iod-server",
        "makeWNameServer(serverIodineServer4Addr, 0.0, zonePwndCom4)",
      )
    )

    self.topo = combined_topo
    self.undef_addrs = ["iod-monitor-addr", "irc-monitor-addr"]
    self.client_addrs = client_addrs

    # Need to bind: uniq_addrs, uniq_nodes (dicts)

  def to_init_maude(self) -> str:

    thispath = pathlib.Path(__file__).resolve()
    libpath = (thispath.parent.parent.parent / "lib").resolve()

    preamble = [
        "set clear rules off .",
        "set print attribute off .",
        "set show advisories off .",
    ]

    sloads = [
        f"sload {libpath / "irc/irc-mamodel-v2.maude"}",
        f"sload {libpath / "webtunnel/webtunnel_prob.maude"}",
        f"sload {libpath / "irc/irc_prob-v2"}",
        f"sload {libpath / "irc/ircMonitor"}",
        f"sload {libpath / "irc/irc-byteseq-interface"}",
        f"sload {libpath / "common/maude/irc-action-actor-v2.maude"}",
        f"sload {libpath / "irc/common/irc_name"}",
        f"sload {libpath / "irc/common/_aux"}",
        f"sload {libpath / "irc/common/app_chat"}",
        f"sload {libpath / "irc/_irc_aux"}",
        f"sload {libpath / "../deps/dns_formalization/Maude/common/apmaude.maude"}",
        f"sload {libpath / "obfs4/_obfs4_aux.maude"}",
        f"sload {libpath / "obfs4/obfs4_prob.maude"}",
        f"sload {libpath / "common/maude/user-action-actor"}",
        f"sload {libpath / "raceboatMastodon/maude/enc-dec-actor"}",
        f"sload {libpath / "raceboatMastodonBidir/maude/rb-cm-bidir-mas.maude"}",
        f"sload {libpath / "mastodon/maude/probabilistic/mastodon"}",
        f"sload {libpath / "raceboatMastodon/maude/user_models/client_config_mastodon_bidi"}",
        f"sload {libpath / "raceboatMastodon/maude/user_models/server_config_mastodon_bidi"}",
        f"sload {libpath / "common/maude/http-overhead.maude"}",
        f"sload {libpath / "cp3-tests/skyhook/skyhook-um-mamodel-1"}",
        f"sload {libpath / "irc/common/irc-msg-model"}",
        f"sload {libpath / "raceboatSkyhook/maude/rb-cm-simple-bi"}",
        f"sload {libpath / "skyhook/skyhook_prob"}",
        f"sload {libpath / "s3/s3_protocol"}",
        f"sload {libpath / "dns/maude/probabilistic/iodine_dns.maude"}",
        f"sload {libpath / "dns/maude/common/_aux.maude"}",
        f"sload {libpath / "network/net_prob.maude"}",
        f"sload {libpath / "common/maude/structured-addresses.maude"}",

        "--- TGEN Includes",
        f"sload {libpath / "tgen/maude/ftp/profiles/ftp-medium-tgen-mamodel-v2.maude"}",
        f"sload {libpath / "common/maude/tgen-action-actor-v2.maude"}",
        f"sload {libpath / "tgen/maude/ftp/ftpTgen-actor.maude"}",
        f"sload {libpath / "tgen/maude/ftp/ftpServer-actor.maude"}",

        f"sload {libpath / "tgen/maude/gorillachat/profiles/gorilla-tgen-mamodel-v2.maude"}",
        f"sload {libpath / "tgen/maude/gorillachat/gorilla-Tgen-actor.maude"}",

        f"sload {libpath / "tgen/maude/minio/profiles/minio-medium-tgen-mamodel-v2.maude"}",
        f"sload {libpath / "tgen/maude/minio/minioTgen-actor.maude"}",
        f"sload {libpath / "s3/s3_protocol.maude"}",

        f"sload {libpath / "tgen/maude/dnsTgen-actor.maude"}",
        f"sload {libpath / "tgen/maude/dnsprofiles/markov/config_fast_1.maude"}",

        f"sload {libpath / "tgen/maude/masTGen.maude"}",
        f"sload {libpath / "tgen/maude/mastodonprofiles/markov/config_influencer_4.maude"}",

        f"sload {libpath / "tgen/maude/irc/ircTgen-actor.maude"}",
    ]

    mod_start_and_includes = [
        "mod HCS_TEST is",

        *indent(1, [
            "pr SCHEDULER .",
            "pr USER-ACTION-ACTOR .",
            "pr SKYHOOK-UM-MAMODEL-1 .",
            "pr IRC-V2 .",
            "pr IRC-MAMODEL-V2 .",
            "pr IRC-USER-ACTION-ACTOR-V2 .",
            "pr IRC-BYTESEQ-INTERFACE .",
            "pr CONTENT-MANAGER-SIMPLE-BI .",
            "inc ENC-DEC .",
            "inc CONTENT-MANAGER-BIDIR .",
            "inc MASTODON .",
            "inc MASTODON-CLIENT-CONFIG-MASTODON-BIDI-MAMODEL .",
            "inc MASTODON-SERVER-CONFIG-MASTODON-BIDI-MAMODEL .",
            "pr SKYHOOK .",
            "pr S3_PROTOCOL .",
            "pr IRC_MONITOR .",
            "pr OBFS4 .",
            "pr APP_CHATS .",
            "pr IRC_NODE .",
            "pr WEBTUNNEL .",
            "pr IRC_NAMES .",
            "pr IODINE_NODE .",
            "pr IODINE_DNS .",
            "pr TCP_SOCKET .",
            "pr NETWORK_NODE .",
            "pr NETWORK_CONNECTION .",
            "inc STRUCTURED-ADDRESSES .",

            "--- TGEN Modules",
            "inc FTP-MEDIUM-MAMODEL-V2 .",
            "inc USER-ACTION-ACTOR-V2 .",
            "inc FTP-TGEN .",
            "inc FTP-SERVER .",

            "inc GORILLA-GORILLA-MAMODEL-V2 .",
            "inc GORILLACHAT-TGEN .",

            "inc MINIO-MEDIUM-MAMODEL-V2 .",
            "inc MINIO-TGEN .",

            "inc DNS-TGEN .",
            "inc DNS-CONFIG-FAST-1-MAMODEL .",

            "inc MAS-TGEN .",
            "inc MASTODON-CONFIG-INFLUENCER-4-MAMODEL .",
            "inc IRC-TGEN .",])
    ]

    params = indent(1, [
        'vars j : Nat .',

        'eq encOH(fsize:Nat,ksize:Nat) = 0 .',
        'eq noiseMin(msg:Msg)          = 0.001 .',
        '***** Global constants  ',
        '**** the user model database',
        'eq MAModelMap                 = ("irc-test" |-> irc-mamodel-v2, "irc-tgen" |-> irc-irc-ma-v2, "ftp" |-> ftp-medium-ma-v2, "gorilla" |-> gorilla-gorilla-ma-v2, "minio" |-> minio-medium-ma-v2) .',
        '*** for the default case',
        'eq noiseMax(msg:Msg)          = 0.00001 .',

        'eq packetSize                 = 1000 .',
        'eq maxPacketSize              = 967 .',

        'op ed-images : -> ByteSeqL .',
        'eq ed-images =',
        *indent(1, [
            'image(1, 3779, 500)',
            ':: image(2, 2405, 1000)',
            ':: image(3, 36861, 1000)',
            ':: image(4, 25377, 500)',
            ':: image(5, 2440, 300)',
            ':: image(6, 1275, 300)',
            ':: image(7, 7710, 1000)',
            ':: image(8, 3577, 500)',
            ':: image(9, 3415, 300)',
            ':: image(10, 74123, 600)',]),
        '.',
    ])

    nameservers = indent(1, [
      "op zonePwndCom4 : -> List{Record} .",
      "eq zonePwndCom4 =",
      *indent(1, [
          "< 'pwnd . 'com . root, soa, 360000.0, soaData(360000.0) >",
          "< 'pwnd . 'com . root, ns, 360000.0, 'ns . 'pwnd . 'com . root >",
          "< 'ns . 'pwnd . 'com . root, a, 360000.0, iod-server-addr >",
          "< 'www0 . 'pwnd . 'com . root, a, 360000.0, 2 . 0 . 1 . 2 >",
          "< 'www1 . 'pwnd . 'com . root, a, 360000.0, 2 . 1 . 1 . 2 >",
          "< wildcard . 'pwnd . 'com . root, txt, 360000.0, nullAddr > .",]),
      "--- \"SBELT\": fallback if there are no known name servers",
      # "op sb : -> ZoneState .",
      # "eq sb = < root ('a . 'root-servers . 'net . root |-> rootDnsAddr) >",
      # ".",
    ])

    resolver_caches = indent(1, [
      "--- Caches",
      "op resolverCache : -> Cache .",
      "eq resolverCache =",
      "cacheEntry(< root, ns, 3600.0, 'a . 'root-servers . 'net . root >, 1)",
      # "cacheEntry(< 'a . 'root-servers . 'net . root, a, 3600.0, rootDnsAddr >, 1)",
      "cacheEntry(< 'com . root, ns, 3600.0, 'ns . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'com . root, a, 3600.0, tldDnsAddr >, 1)",
      "cacheEntry(< 'pwnd . 'com . root, ns, 3600.0, 'ns . 'pwnd . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'pwnd . 'com . root, a, 3600.0, authDnsAddr >, 1)",
      "cacheEntry(< 'internet . 'com . root, ns, 3600.0, 'ns . 'internet . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'internet . 'com . root, a, 3600.0, authDnsAddr >, 1)",
      "cacheEntry(< 't1 . 'pwnd . 'com . root, ns, 3600.0, 'ns . 't1 . 'pwnd . 'com . root >, 1)",
      "cacheEntry(< 'ns . 't1 . 'pwnd . 'com . root, a, 3600.0, iod-server-addr >, 1)",
      "cacheEntry(< 'corp1 . 'com . root, ns, 3600.0, 'ns . 'corp1 . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'corp1 . 'com . root, a, 3600.0, corp1DnsAddr >, 1)",
      "cacheEntry(< 'corp2 . 'com . root, ns, 3600.0, 'ns . 'corp2 . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'corp2 . 'com . root, a, 3600.0, corp2DnsAddr >, 1)",
      "cacheEntry(< 'corp3 . 'com . root, ns, 3600.0, 'ns . 'corp3 . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'corp3 . 'com . root, a, 3600.0, corp3DnsAddr >, 1)",
      "cacheEntry(< 'corp4 . 'com . root, ns, 3600.0, 'ns . 'corp4 . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'corp4 . 'com . root, a, 3600.0, corp4DnsAddr >, 1)",
      "cacheEntry(< 'corp5 . 'com . root, ns, 3600.0, 'ns . 'corp5 . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'corp5 . 'com . root, a, 3600.0, corp5DnsAddr >, 1)",
      "cacheEntry(< 'serv . 'com . root, ns, 3600.0, 'ns . 'serv . 'com . root >, 1)",
      # "cacheEntry(< 'ns . 'serv . 'com . root, a, 3600.0, servDnsAddr >, 1)",
      ".",
    ])

    address_names = list(map(lambda x: x.addr.name, self.topo.nodes))
    address_decls = indent(1, [
        "ops",
        *indent(1, address_names),
        ": -> Address .",
    ])

    def tempfunc(node):
      print('wtfbro')
      if node.name == "":
        print(node)
      return f"eq {node.addr.name} = {node.addr.maude} ."

    address_defs = indent(1, 
        list(map(
            tempfunc,
            # lambda node: f"eq {node.addr.name} = {node.addr.maude} .",
            self.topo.nodes))
    )

    linktype_params = indent(1, [
        'eq transport(any:Address) = tcp(any:Address) .',
        '',
        'vars dt : Float .',
        'vars icAddr isAddr ifsAddr : Address .',
        'vars room : String .',
        'op mkJoin : Float String Address Address Address -> ScheduleMsg .',
        'eq mkJoin(dt,room,icAddr, isAddr, ifsAddr) =',
        *indent(1, [
            '[dt,',
            '(to isAddr from ifsAddr :',
            'JoinChannel(makeIrcChannelName(room), icAddr )),',
            '0]',]),
        '.',
    ])

    linktypes = self.topo.get_link_types()
    linktype_decls = indent(1, [
        "ops",
        *indent(1, list(map(lambda ltyp: ltyp.name(), linktypes))),
        ": -> AttributeSet .",
    ])

    linktype_defs = indent(1,
        list(map(
            lambda ltyp: f"eq {ltyp.name()} = {ltyp.maude()} .",
            linktypes
        ))
    )
    
    linkdata_defs = indent(1, [
        "eq LinkData =",
        *indent(1, list(map(
            lambda lnk: lnk.maude(),
            self.topo.links
        ))),
        "."
    ])

    actor_decls = indent(1, [
        "ops",
        *indent(1, list(map(
            lambda node: node.name,
            self.topo.nodes
        ))),
        ": -> Actor ."
    ])

    actor_defs = indent(1,
        list(map(
            lambda node: f"eq {node.name} = {node.maude} .",
            self.topo.nodes
        ))
    )

    adversary_def = indent(1, [
        "op advAddr : -> Address .",
        "op advActor : -> Actor .",
        "eq advActor = mkAdversaryCp3(advAddr) .",
    ])

    init_state_start = indent(1, [
        "op initState : Nat -> Config .",
        "eq initState(j) =",
        *indent(1, [
            "rCtr(j + 8)",
            *map(lambda node: node.name, self.topo.nodes),
        ]),          
    ])

    # TODO: write these properly with loops for each subnet
    trigger_msgs = indent(2, [
        # '[0.001, (to aha3Addr from aha3Addr : SkyhookStartCmd), 0]',
        # '[0.20, (to wtClient1Addr from wtClient1Addr : WtStartCmd), 0]',
        # '[1.0 + genRandomX(j, 0.0, 0.0001), (to umac3Addr from umac3Addr : actionR("ok")), 0]',
        # '[1.0 + genRandomX(s s j, 0.0, 0.0001), (to umas3Addr from umas3Addr : actionR("ok")), 0]',
        # '[1.0 + genRandomX(j, 0.0, 0.0001), (to umac5Addr from umac5Addr : actionR("ok")), 0]',
        # '[1.0 + genRandomX(s s j, 0.0, 0.0001), (to umas5Addr from umas5Addr : actionR("ok")), 0]',
        '--- TGEN Starts',
        # '[30.0 + genRandomX(j, 0.0, 0.0001), (to ftpUMAddr from ftpUMAddr : burstDelayTO), 0]',
        # '[30.0 + genRandomX(j, 0.0, 0.0001), (to gorillaUMAddr from gorillaUMAddr : burstDelayTO), 0]',
        # '[30.0 + genRandomX(j, 0.0, 0.0001), (to minioUMAddr from minioUMAddr : burstDelayTO), 0]',
        # '[30.0 + genRandomX(j, 0.0, 0.0001), (to dnsUMAddr from dnsUMAddr : actionR("")), 0]',
        '[30.0 + genRandomX(j, 0.0, 0.0001), (to mast-tgen-usermodel-addr-0 from mast-tgen-usermodel-addr-0 : actionR("")), 0]',
        # '[30.0 + genRandomX(j, 0.0, 0.0001), (to ircTgenUMAddr from ircTgenUMAddr : burstDelayTO), 0]',
        # 'mkJoin(2.0, "#chat", ircClient1Addr, ircServerAddr, server1IfaceAddr)',
        # 'mkJoin(2.1, "#general", ircClient1Addr, ircServerAddr, server1IfaceAddr)',
        # 'mkJoin(2.2, "#random", ircClient1Addr, ircServerAddr, server1IfaceAddr)',
        # 'mkJoin(2.3, "#chat", ircClient2Addr, ircServerAddr, server2IfaceAddr)',
        # 'mkJoin(2.4, "#general", ircClient2Addr, ircServerAddr, server2IfaceAddr)',
        # 'mkJoin(2.5, "#random", ircClient2Addr, ircServerAddr, server2IfaceAddr)',
        # 'mkJoin(2.6, "#chat", ircClient3Addr, ircServerAddr, server3IfaceAddr)',
        # 'mkJoin(2.7, "#general", ircClient3Addr, ircServerAddr, server3IfaceAddr)',
        # 'mkJoin(2.8, "#random", ircClient3Addr, ircServerAddr, server3IfaceAddr)',
        # 'mkJoin(2.9, "#chat", ircClient4Addr, ircServerAddr, serverIface4Addr)',
        # 'mkJoin(3.0, "#general", ircClient4Addr, ircServerAddr, serverIface4Addr)',
        # 'mkJoin(3.1, "#random", ircClient4Addr, ircServerAddr, serverIface4Addr)',
        # 'mkJoin(3.2, "#chat", ircClient5Addr, ircServerAddr, server5IfaceAddr)',
        # 'mkJoin(3.3, "#general", ircClient5Addr, ircServerAddr, server5IfaceAddr)',
        # 'mkJoin(3.4, "#random", ircClient5Addr, ircServerAddr, server5IfaceAddr)',
        # 'mkJoin(3.5, "#tgen_chat", ircTgenClientAddr, ircServerAddr, ircTgenClientAddr)',
        # 'mkJoin(3.6, "#tgen_general", ircTgenClientAddr, ircServerAddr, ircTgenClientAddr)',
        # 'mkJoin(3.7, "#tgen_random", ircTgenClientAddr, ircServerAddr, ircTgenClientAddr)',
        # '[20.0, (to ircClient1UserModelAddr from ircClient1UserModelAddr : burstDelayTO), 0]',
        # '[21.0, (to ircClient2UserModelAddr from ircClient2UserModelAddr : burstDelayTO), 0]',
        # '[22.0, (to ircClient3UserModelAddr from ircClient3UserModelAddr : burstDelayTO), 0]',
        # '[23.0, (to ircClient4UserModelAddr from ircClient4UserModelAddr : burstDelayTO), 0]',
        # '[24.0, (to ircClient5UserModelAddr from ircClient5UserModelAddr : burstDelayTO), 0]',
    ])

    client_names = list(map(lambda x: x.name, self.client_addrs))
    mod_finale = [
        *indent(1, [
            "op slimit : -> Float .",
            "eq slimit = 1000.0 .",

            "op initConfig : -> Config .",
            "rl[init]: initConfig => run({0.0 | nil} initState(counter), slimit) .",
            "op allClientsAddr : -> AddrList .",
            f"eq allClientsAddr = {" ; ".join(client_names)} .",]),

        "endm",
    ]

    file_finale = [
        "set print attribute on .",
        "rew initConfig .",
        "q",
    ]

    return '\n'.join([
        *preamble, "",
        *sloads, "",
        *mod_start_and_includes, "",
        *params, "",
        *nameservers, "",
        *address_decls, "",
        *address_defs, "",
        *linktype_params, "",
        *linktype_decls, "",
        *linktype_defs,
        *linkdata_defs,
        *actor_decls,
        *actor_defs,
        *adversary_def,
        # tgen_decls,
        # tgen_defs,
        *init_state_start,
        *trigger_msgs,
        *indent(1, ["."]),
        *mod_finale,"",
        *file_finale,
    ])