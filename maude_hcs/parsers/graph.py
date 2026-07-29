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

import json
import networkx as nx
import logging

from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from collections.abc import Callable

from typing import Any, Dict

from maude_hcs.lib.common.address import Address

logger = logging.getLogger(__name__)

IXP_ADDR_NAME = "IXP-DEFAULT-ADDR"

def default_loss() -> dict[str, float]:
  return {'p13': 0.0, 'p31': 0.0, 'p32': 0.0, 'p23': 0.0, 'p14': 0.0}

@dataclass_json
@dataclass
class Node:
  """Represents a Maude network actor"""
  addr: Address
  label: str
  maude: str

@dataclass_json
@dataclass
class Link: 
  """Represents a network link between two Maude network actors"""
  src: Node | None  # if src is None, assumed to be ixp
  dst: Node | None  # ditto
  label: str
  latency: float = 0.0

  # Loss probability:
  loss: dict[str, float] = field(default_factory = default_loss)

  def has_same_endpoints(self, other):
    return self.src == other.src and self.dst == other.dst

  def is_similar_to(self, other):
      return self.latency == other.latency and self.loss == other.loss    

class Counter:
  """A counter that returns and increments the current count each time its called"""
  def __init__(self, start: int):
    self.i = start

  def __call__(self):
    result = self.i
    self.i += 1
    return self.i


@dataclass_json
@dataclass
class Topology:
    isDirected: bool
    nodes: list[Node] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    def getNodebyLabel(self, label):
      for node in self.nodes:
        if node.label == label:
          return node

    def merge(self, other):
      assert set(self.nodes).intersection(set(other.nodes)) == {None}, "topologies to be merged should only have IXP node in common"
      nodes = self.nodes + other.nodes

      links = self.links + other.links
      assert len(links) == len(self.links) + len(other.links), "topologies to be merged should not have links in common"
      assert self.isDirected == other.isDirected, "topologies to be merged should have same directionality"

      return Topology(self.isDirected, nodes, links)

    @staticmethod
    def merge_all(topos):
      assert len(topos) > 0, "list of topologies to merge must be non-empty"
      result = topos[0]
      for topo in topos[1:]:
        result = result.merge(topo)
      return result

    @staticmethod
    def from_yml_and_loss(yml: Dict[Any, Any], loss_specs: Dict[Any, Any]) -> "Topology":
      subnet_idx = Counter(0)

      yml_networks = yml["network"]
      yml_nodes = yml["nodes"]
      yml_tgens = yml["tgen"]

      irc_server_addr = Address("irc_server_addr", "a(srvN,srv,irc,srv,0)")
      irc_server = Node(irc_server_addr, "irc_server", f"mkIrcServer({irc_server_addr.name})")

      # racetunnel_topo = mk_racetunnel_topo(networks, nodes, tgen, loss_specs)
      # sky_topo = mk_sky_topo(networks, nodes, tgen, loss_specs)
      # obfs_topo = mk_obfs_topo(networks, nodes, tgen, loss_specs)
      # iodine_topo = mk_iodine_topo(networks, nodes, tgen, loss_specs)
      mastodon_topo = mk_mastodon_topo(yml_networks, yml_nodes, yml_tgens, loss_specs, irc_server, subnet_idx())

      return Topology.merge_all([
        # racetunnel_topo,
        # sky_topo,
        # obfs_topo,
        # iodine_topo,
        mastodon_topo
      ])

      for (net_name, net_topo) in tne_network.items():
        if net_name == "router_net": continue # Already handled ixp net above

        net_params = yml["network"][net_name]["params"]

        up_loss_name = net_params["upstream"]["loss_profile"]
        up_latency = net_params["upstream"]["latency"]
        up_loss = loss_specs[up_loss_name]

        down_loss_name = net_params["downstream"]["loss_profile"]
        down_latency = net_params["downstream"]["latency"]
        down_loss = loss_specs[down_loss_name]

        for (label, addr) in net_topo["container_info"].items():
          node = Node.from_label(next_id, label)
          node.ip_address = addr
          nodes.append(node)
          next_id += 1

          uplink = Link(
            src_id=node.id, src_label=node.label,
            dst_id=ixp_router.id, dst_label=ixp_router.label,
            label=f"{node.label}>{ixp_router.label}",
            latency=up_latency, loss=up_loss
          )

          downlink = Link(
            src_id=ixp_router.id, src_label=ixp_router.label,
            dst_id=node.id, dst_label=node.label,
            label=f"{ixp_router.label}>{node.label}",
            latency=down_latency, loss=down_loss
          )

          links.extend([uplink, downlink])

      return Topology(isDirected=True, nodes=nodes, links=links)


def mk_mastodon_topo(
    yml_networks: Dict[Any, Any], 
    yml_nodes: Dict[Any, Any],
    yml_tgens: Dict[Any, Any],
    loss_specs: Dict[str, Dict[str, float]],
    irc_server: Node,
    subnet_idx: int,
) -> (Address, Address, Topology):
  """
  Create the chunk of the final network topology corresponding to (most) Mastodon traffic.
  Doesn't include tgens, since those are spread throughout all the networks.
  They are added to the final network topology in a separate step, using the returned addresses.

  Returns:
    - the primary router address for the mastodon client subnet,
    - the primary router for the mastodon server subnet,
    - the topology chunk for mastodon traffic
  """

  nodes = []
  links = []

  client_subnet_config = yml_networks["client_net_mastodon"]["params"]

  client_up_latency = client_subnet_config["upstream"]["latency"]
  client_down_latency = client_subnet_config["downstream"]["latency"]

  client_up_loss = loss_specs[client_subnet_config["upstream"]["loss_profile"]]
  client_down_loss = loss_specs[client_subnet_config["downstream"]["loss_profile"]]

  # Create the static actor addresses (these are always basically the same, regardless of how many active hcs clients there are)
  mast_server_iface_addr = Address("mast_server_iface_addr", f"a(srvN[{subnet_idx}],hcs,irc,if,1)")
  mast_umas_addr = Address("mast_umas_addr", f"a(srvN{subnet_idx},hcs,mas,um,1)")
  mast_cmas_addr = Address("mast_cmas_addr", f"(srvN[{subnet_idx}],hcs,mas,cm,1)")
  mast_mcas_addr = Address("mast_mcas_addr", f"a(srvN[{subnet_idx}],hcs,mas,mc,1)")
  mast_edas_addr = Address("mast_edas_addr", f"a(srvN[{subnet_idx}],hcs,mas,ed,1)")
  mast_server_netclient_addr = Address("mast_server_netclient_addr", f"a(srvN[{subnet_idx}],tcp,mas,cl,1)")
  mast_server_addr = Address("mast_server_addr", f"a(masN,tcp,mas,srv,1)")
  mast_subnet_router_addr = Address("mast_subnet_router_addr", f"a(masN,srv,mas,srv,1)")

  # Create the actual static actors
  mast_server_iface = Node(
    mast_server_iface_addr, 
    "mast_server_iface", 
    f"mkIrcByteSeqIface({mast_server_iface_addr.name}, {irc_server.addr.name}, {mast_cmas_addr.name})")
  mast_umas = Node(
    mast_umas_addr,
    "mast_umas",
    f"mkUMactor({mast_umas_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmas_addr.name})")
  mast_cmas = Node(
    mast_cmas_addr,
    "mast_cmas",
    f'mkCMSndRcvActor({mast_cmas_addr.name}, {mast_edas_addr.name}, {mast_mcas_addr.name}, {mast_server_iface_addr.name}, "server5", "client5")')
  mast_mcas = Node(
    mast_mcas_addr,
    "mast_mcas",
    f"makeMastodonClient({mast_mcas_addr.name}, {mast_subnet_router_addr.name}, {mast_cmas_addr.name})")
  mast_edas = Node(
    mast_edas_addr,
    "mast_edas",
    f"makeDestiniActor({mast_edas_addr.name}, ed-iamges)")
  mast_server = Node(
    mast_server_addr,
    "mast_server",
    f"makeNetServer({mast_server_addr.name}, {mast_subnet_router_addr.name})")
  mast_server_netclient = Node(
    mast_server_netclient_addr,
    "mast_server_netclient",
    f"makeNetClient({mast_server_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcas_addr.name}, true, nullAddr, nullName)")
  mast_subnet_router = Node(
    mast_subnet_router_addr,
    "mast_subnet_router",
    f"makeMastodonServer({mast_subnet_router_addr.name})")

  nodes += [mast_server_iface, mast_umas, mast_cmas, mast_mcas, mast_edas, mast_server, mast_server_netclient, mast_subnet_router]

  hcs_config = yml_nodes["node_type_mastodon"]
  num_hcs_clients = hcs_config["client_per_network"]["client_net_mastodon"]["quantity"]

  actor_idx = Counter(0)

  for _ in range(len(num_hcs_clients)):
    idx = actor_idx()
    mast_client_addr = Address(f"mast_client_addr_{idx}", f"a(cl[{subnet_idx}],hcs,irc,cl,1)")
    mast_client_user_model_addr = Address(f"mast_client_user_model_addr_{idx}", f"a(cl[{subnet_idx}],hcs,irc,um,1)")
    mast_client_iface_addr = Address(f"mast_client_iface_addr_{idx}", f"a(cl[{subnet_idx}],hcs,irc,if,1)")
    mast_umac_addr = Address(f"mast_umac_addr_{idx}", f"a(cl[{subnet_idx}],hcs,mas,um,{idx})")
    mast_cmac_addr = Address(f"mast_cmac_addr_{idx}", f"a(cl[{subnet_idx}],hcs,mas,cm,1)")
    mast_mcac_addr = Address(f"mast_mcac_addr_{idx}", f"a(cl[{subnet_idx}],hcs,mas,mc,1)")
    mast_edac_addr = Address(f"mast_edac_addr_{idx}", f"a(cl[{subnet_idx}],hcs,mas,ed,1)")
    mast_client_netclient_addr = Address(f"mast_client_netclient_addr_{idx}", f"a(cl[{subnet_idx}],tcp,mas,cl,1)")


    # eq client5Iface        = mkIrcByteSeqIface(client5IfaceAddr, ircClient5Addr, cmac5Addr) .
    # eq umac5Act            = mkUMactor(umac5Addr, mastodon-client-config-mastodon-bidi-ma, cmac5Addr) .
    # eq cmac5Act            = mkCMSndRcvActor(cmac5Addr, edac5Addr, mcac5Addr, client5IfaceAddr, "client5", "server5") .
    # eq mcac5Act            = makeMastodonClient(mcac5Addr, masSrvAddr, cmac5Addr) .
    # eq edac5Act            = makeDestiniActor(edac5Addr, ed-images) .
    # eq mastodonClient5NetClient = makeNetClient(mastodonClient5NetClientAddr, masSrvAddr, mcac5Addr, true, nullAddr, nullName) .
  
    mast_client = Node(
      mast_client_addr, 
      f"mast_client_{idx}", 
      f"mkIrcClient-v2({mast_client_addr.name}, {mast_client_iface_addr.name}, \"Client{subnet_idx}\")")
    mast_client_user_model = Node(
      mast_client_user_model_addr, 
      f"mast_client_user_model_{idx}", 
      f"mkIrcUMV2Actor({mast_client_user_model_addr.name}, \"irc-test\", {mast_client_addr.name})")
    mast_client_iface = Node(
      mast_client_iface_addr, 
      f"mast_client_iface_{idx}", 
      f"mkIrcByteSeqIface({mast_client_iface_addr.name}, {mast_client_addr.name}, {mast_cmac_addr.name})")
    mast_umac = Node(
      mast_umac_addr, 
      f"mast_umac_{idx}", 
      f"mkUMactor({mast_umac_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmac_addr.name})")
    mast_cmac = Node(
      mast_cmac_addr, 
      f"mast_cmac_{idx}", 
      f'mkCMSndRcvActor({mast_cmac_addr.name}, {mast_edac_addr.name}, {mast_mcac_addr.name}, {mast_client_iface_addr.name}, "client{idx}", "server5")')
    mast_mcac = Node(
      mast_mcac_addr, 
      f"mast_mcac_{idx}", 
      f"makeMastodonClient({mast_mcac_addr.name}, {mast_subnet_router_addr.name}, {mast_cmac_addr.name})")
    mast_edac = Node(
      mast_edac_addr, 
      f"mast_edac_{idx}", 
      f"makeDestiniActor({mast_edac_addr.name}, ed-images)")
    mast_client_netclient = Node(
      mast_client_netclient_addr, 
      f"mast_client_netclient_{idx}", 
      f"makeNetClient({mast_client_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcac_addr.name}, true, nullAddr, nullName)")

    nodes += [mast_client, mast_client_user_model, mast_client_iface, mast_umac, mast_cmac, mast_mcac, mast_edac, mast_client_netclient]


  aaa(masSrvAddr, mcac5Addr, LinkType-TCP-4stateLoss)
  aaa(masSrvAddr, mcas5Addr, LinkType-TCP-4stateLoss)
  aaa(mcac5Addr, masSrvAddr, LinkType-TCP-4stateLoss)
  aaa(mcas5Addr, masSrvAddr, LinkType-TCP-4stateLoss) 
  aaa(wtProxy1Addr, IXP-DEFAULT-ADDR, LinkType-TCP-4stateLoss)
  aaa(IXP-DEFAULT-ADDR, wtProxy1Addr, LinkType-TCP-4stateLoss)
  aaa(wtClient1Addr, IXP-DEFAULT-ADDR, LinkType-TCP-4stateLoss)
  aaa(IXP-DEFAULT-ADDR, wtClient1Addr, LinkType-TCP-4stateLoss)




  # create fixed nodes
  # create tgens
