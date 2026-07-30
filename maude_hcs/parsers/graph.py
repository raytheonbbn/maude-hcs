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

import logging

from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from collections.abc import Callable

from typing import Any, Dict

logger = logging.getLogger(__name__)

def default_loss() -> dict[str, float]:
  return {'p13': 0.0, 'p31': 0.0, 'p32': 0.0, 'p23': 0.0, 'p14': 0.0}

# Note: any dataclass below with a name represents a maude variable *binding*, not just
# the maude value itself. In other words, it represents a maude object that should be bound
# to 'name' in the resulting maude file. Sometimes these objects may be used like plain maude values, however

@dataclass_json
@dataclass(frozen=True)
class IpAddress:
    octets: list[int]

@dataclass_json
@dataclass(frozen=True)
class Address:
    name: str   # Variable name for this address in Maude
    maude: str  # Maude code to construct this address
    ip: IpAddress | None = None

@dataclass_json
@dataclass(frozen=True)
class Node:
  """Represents a Maude network actor"""
  addr: Address
  name: str
  maude: str

@dataclass_json
@dataclass(frozen=True)
class LinkType:
  """Represents qualities of a network link (loss transition probabilities)"""
  name: str
  p13: float = 0.0
  p31: float = 0.0
  p32: float = 0.0
  p23: float = 0.0
  p14: float = 0.0
  latency: float = 0.0

  def maude(self) -> str:
    return (
      "(4stateLoss:"
      f"  (p13: {self.p13},"
      f"  p31: {self.p31},"
      f"  p32: {self.p32},"
      f"  p23: {self.p23},"
      f"  p14: {self.p14},"
      f"  oneWayDelay: {self.latency})"
      ")"
    )
  
  @staticmethod
  def from_yml(name, yml: dict[str, Any], latency: float = 0.0) -> "LinkType":
    return LinkType(name, yml["p13"], yml["p31"], yml["p32"], yml["p23"], yml["p14"], latency)

  # To allow sorting, which allows us to give deterministic order for uniquified lists of linktypes
  def __lt__(self, other: "LinkType") -> bool:
    return self.name < other.name

  
@dataclass_json
@dataclass(frozen=True)
class Link: 
  """Represents a network link between two Maude network actors"""
  src: Node | None  # if src is None, assumed to be ixp
  dst: Node | None  # ditto
  type: LinkType = field(default_factory = lambda: LinkType("PerfectLinkType"))

  def has_same_endpoints(self, other: "Link") -> bool:
    return self.src == other.src and self.dst == other.dst

  def is_similar_to(self, other: "Link") -> bool:
      return self.type == other.type

  def maude(self) -> str:
    return f"aaa({self.src.addr.name if self.src else "IXP-DEFAULT-ADDR"}, {self.dst.addr.name if self.dst else "IXP-DEFAULT-ADDR"}, {self.type.name})"

class Counter:
  """A counter that returns and increments the current count each time its called"""
  def __init__(self, start: int):
    self.i = start

  def __call__(self) -> int:
    result = self.i
    self.i += 1
    return result

@dataclass_json
@dataclass
class Topology:
    isDirected: bool

    # A list of ALL nodes in this topology, whether they appear in the declared links or not.
    nodes: list[Node] = field(default_factory=list)

    # this is a list of DECLARED links, for the purpose of determining link types.
    # Implicitly, any node can communicate with any other.
    links: list[Link] = field(default_factory=list)

    def __post_init__(self):
      self.validate()

    def validate(self):
      assert len(self.nodes) == len(set(self.nodes)), "Topology instance should not contain duplicate nodes"
      assert len(self.links) == len(set(self.links)), "Topology instance should not contain duplicate links"

      link_nodes = []
      for link in self.links:
        if link.src is not None: link_nodes.append(link.src)
        if link.dst is not None: link_nodes.append(link.dst)

      assert set(link_nodes).issubset(self.nodes), "every endpoint in self.links must also be in self.nodes"

    def get_node_by_name(self, name: str):
      for node in self.nodes:
        if node.name == name:
          return node

    def get_link_types(self) -> list[LinkType]:
      return sorted(list(set(map(lambda lnk: lnk.type, self.links))))

    def merge(self, other: "Topology") -> "Topology":
      assert set(self.nodes).intersection(set(other.nodes)) == {None}, "topologies to be merged should only have IXP node in common"
      nodes = self.nodes + other.nodes

      links = self.links + other.links
      assert len(links) == len(self.links) + len(other.links), "topologies to be merged should not have links in common"
      assert self.isDirected == other.isDirected, "topologies to be merged should have same directionality"

      return Topology(self.isDirected, nodes, links) 

    @staticmethod
    def merge_all(topos: list["Topology"]) -> "Topology":
      assert len(topos) > 0, "list of topologies to merge must be non-empty"
      result = topos[0]
      for topo in topos[1:]:
        result = result.merge(topo)
      return result

    @staticmethod
    def from_yml_and_loss(yml: Dict[Any, Any], loss_specs: Dict[Any, Any]) -> tuple["Topology", list[Address]]:
      """Returns Topology and list of client addresses"""
      subnet_idx = Counter(0)

      yml_networks = yml["network"]
      yml_nodes = yml["nodes"]
      yml_tgens = yml["tgen"]

      irc_server_addr = Address("irc_server_addr", "a(srvN,srv,irc,srv,0)")
      irc_server = Node(irc_server_addr, "irc_server", f"mkIrcServer({irc_server_addr.name})")

      # (racetunnel_topo = mk_racetunnel_topo(networks, nodes, tgen, loss_specs)
      # sky_topo = mk_sky_topo(networks, nodes, tgen, loss_specs)
      # obfs_topo = mk_obfs_topo(networks, nodes, tgen, loss_specs)
      # (iodine_topo, iodine_server_addr, iodine_client_addrs) = mk_iodine_topo(yml_networks, yml_nodes, yml_tgens, loss_specs, irc_server, subnet_idx())
      (mastodon_topo, mastodon_server_addr, mastodon_client_addrs) = mk_mastodon_topo(yml_networks, yml_nodes, yml_tgens, loss_specs, irc_server, subnet_idx())
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

      return (combined_topo, client_addrs)


# Following function translated from:

  # Addrs:
  # eq ircClient5Addr = a(cl[5],hcs,irc,cl,1) .
  # eq ircClient5UserModelAddr = a(cl[5],hcs,irc,um,1) .
  # eq client5IfaceAddr = a(cl[5],hcs,irc,if,1) .
  # eq server5IfaceAddr = a(srvN[5],hcs,irc,if,1) .
  # eq umac5Addr = a(cl[5],hcs,mas,um,1) .
  # eq cmac5Addr = a(cl[5],hcs,mas,cm,1) .
  # eq mcac5Addr = a(cl[5],hcs,mas,mc,1) .
  # eq edac5Addr = a(cl[5],hcs,mas,ed,1) .
  # eq umas5Addr = a(srvN[5],hcs,mas,um,1) .
  # eq cmas5Addr = a(srvN[5],hcs,mas,cm,1) .
  # eq mcas5Addr = a(srvN[5],hcs,mas,mc,1) .
  # eq edas5Addr = a(srvN[5],hcs,mas,ed,1) .
  # eq mastodonClient5NetClientAddr = a(cl[5],tcp,mas,cl,1) .
  # eq mastodonServer5NetClientAddr = a(srvN[5],tcp,mas,cl,1) .
  # eq masNetServerAddr = a(masN,tcp,mas,srv,0) .
  # eq masSrvAddr = a(masN,srv,mas,srv,0) .

  # Actors:
  # eq ircClient5          = mkIrcClient-v2(ircClient5Addr, client5IfaceAddr, "Client5") .
  # eq ircClient5UserModel = mkIrcUMV2Actor(ircClient5UserModelAddr, "irc-test", ircClient5Addr) .
  # eq client5Iface        = mkIrcByteSeqIface(client5IfaceAddr, ircClient5Addr, cmac5Addr) .
  # eq umac5Act            = mkUMactor(umac5Addr, mastodon-client-config-mastodon-bidi-ma, cmac5Addr) .
  # eq cmac5Act            = mkCMSndRcvActor(cmac5Addr, edac5Addr, mcac5Addr, client5IfaceAddr, "client5", "server5") .
  # eq mcac5Act            = makeMastodonClient(mcac5Addr, masSrvAddr, cmac5Addr) .
  # eq edac5Act            = makeDestiniActor(edac5Addr, ed-images) .
  
  # eq server5Iface        = mkIrcByteSeqIface(server5IfaceAddr, ircServerAddr, cmas5Addr) .
  # eq umas5Act            = mkUMactor(umas5Addr, mastodon-client-config-mastodon-bidi-ma, cmas5Addr) .
  # eq cmas5Act            = mkCMSndRcvActor(cmas5Addr, edas5Addr, mcas5Addr, server5IfaceAddr, "server5", "client5") .
  # eq mcas5Act            = makeMastodonClient(mcas5Addr, masSrvAddr, cmas5Addr) .
  # eq edas5Act            = makeDestiniActor(edas5Addr, ed-images) .
  
  # eq mastodonClient5NetClient = makeNetClient(mastodonClient5NetClientAddr, masSrvAddr, mcac5Addr, true, nullAddr, nullName) .
  # eq masNetServer      = makeNetServer(masNetServerAddr, masSrvAddr) .
  # eq mastodonServer5NetClient = makeNetClient(mastodonServer5NetClientAddr, masSrvAddr, mcas5Addr, true, nullAddr, nullName) .
  # eq masSrvAct = makeMastodonServer(masSrvAddr) .

  # Constant Links:
  # aaa(masSrvAddr, mcas5Addr, LinkType-TCP-4stateLoss)
  # aaa(mcas5Addr, masSrvAddr, LinkType-TCP-4stateLoss) 

  # aaa(masSrvAddr,       IXP-DEFAULT-ADDR, LinkType-TCP-4stateLossIxp)
  # aaa(IXP-DEFAULT-ADDR, masSrvAddr,       LinkType-TCP-4stateLossIxp)

  # aaa(mcas5Addr,        IXP-DEFAULT-ADDR, LinkType-TCP-4stateLossIxp)
  # aaa(IXP-DEFAULT-ADDR, mcas5Addr,        LinkType-TCP-4stateLossIxp)

  # Per-client links
  # aaa(mcac5Addr,        IXP-DEFAULT-ADDR, LinkType-TCP-4stateLossIxp)
  # aaa(IXP-DEFAULT-ADDR, mcac5Addr,        LinkType-TCP-4stateLossIxp)
  # aaa(masSrvAddr, mcac5Addr, LinkType-TCP-4stateLoss)
  # aaa(mcac5Addr, masSrvAddr, LinkType-TCP-4stateLoss)


def mk_mastodon_topo(
    yml_networks: Dict[Any, Any], 
    yml_nodes: Dict[Any, Any],
    yml_tgens: Dict[Any, Any],
    loss_specs: Dict[str, Dict[str, float]],
    irc_server: Node,
    subnet_idx: int,
) -> tuple[Topology, Node, list[Address]]:
  """
  Create the chunk of the final network topology corresponding to (most) Mastodon traffic.
  This means the entire mastodon server subnet, the HCS actors in the client mastodon subnet, and the links between them and the IXP
  DOES NOT INCLUDE TGENS, since those are spread throughout all the networks.
  They are added to the final network topology in a separate step, using the returned mastodon server node.

  Returns:
    - the topology chunk for mastodon traffic
    - the node for the mastodon server (for use in tgen step)
    - a list of all client addresses in this chunk (for finale maude output)
  """

  nodes = []

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

  client_nodes: dict[str, Node] = {}
  client_addrs: list[Address] = []

  for i in range(num_hcs_clients):
    mast_client_addr = Address(f"mast_client_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,cl,{i})")
    mast_client_user_model_addr = Address(f"mast_client_user_model_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,um,{i})")
    mast_client_iface_addr = Address(f"mast_client_iface_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,if,{i})")
    mast_umac_addr = Address(f"mast_umac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,um,{i})")
    mast_cmac_addr = Address(f"mast_cmac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,cm,{i})")
    mast_mcac_addr = Address(f"mast_mcac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,mc,{i})")
    mast_edac_addr = Address(f"mast_edac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,ed,{i})")
    mast_client_netclient_addr = Address(f"mast_client_netclient_addr_{i}", f"a(cl[{subnet_idx}],tcp,mas,cl,{i})")
    client_addrs.append(mast_client_addr)

    named_nodes = {
      f"mast_client_{i}": Node(
        mast_client_addr, 
        f"mast_client_{i}", 
        f'mkIrcClient-v2({mast_client_addr.name}, {mast_client_iface_addr.name}, "Client{subnet_idx}")'),
      
      f"mast_client_user_model_{i}": Node(
        mast_client_user_model_addr, 
        f"mast_client_user_model_{i}", 
        f'mkIrcUMV2Actor({mast_client_user_model_addr.name}, "irc-test", {mast_client_addr.name})'),

      f"mast_client_iface_{i}": Node(
        mast_client_iface_addr, 
        f"mast_client_iface_{i}", 
        f"mkIrcByteSeqIface({mast_client_iface_addr.name}, {mast_client_addr.name}, {mast_cmac_addr.name})"),

      f"mast_umac_{i}": Node(
        mast_umac_addr, 
        f"mast_umac_{i}", 
        f"mkUMactor({mast_umac_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmac_addr.name})"),

      f"mast_cmac_{i}": Node(
        mast_cmac_addr, 
        f"mast_cmac_{i}", 
        f'mkCMSndRcvActor({mast_cmac_addr.name}, {mast_edac_addr.name}, {mast_mcac_addr.name}, {mast_client_iface_addr.name}, "mast_client_{i}", "mast_server")'),

      f"mast_mcac_{i}": Node(
        mast_mcac_addr, 
        f"mast_mcac_{i}", 
        f"makeMastodonClient({mast_mcac_addr.name}, {mast_subnet_router_addr.name}, {mast_cmac_addr.name})"),

      f"mast_edac_{i}": Node(
        mast_edac_addr, 
        f"mast_edac_{i}", 
        f"makeDestiniActor({mast_edac_addr.name}, ed-images)"),

      f"mast_client_netclient_{i}": Node(
        mast_client_netclient_addr, 
        f"mast_client_netclient_{i}", 
        f"makeNetClient({mast_client_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcac_addr.name}, true, nullAddr, nullName)"),
    }

    nodes += named_nodes.values()
    client_nodes.update(named_nodes)

  server_subnet_config = yml_networks["mastodon_net"]["params"]
  
  server_up_latency = server_subnet_config["upstream"]["latency"]
  server_down_latency = server_subnet_config["downstream"]["latency"]

  server_up_loss = loss_specs[server_subnet_config["upstream"]["loss_profile"]]
  server_down_loss = loss_specs[server_subnet_config["downstream"]["loss_profile"]]

  # TODO: give these the proper linktypes! Ask Christophe exactly how to combine probabilities
  links = [
    Link(mast_subnet_router, mast_mcas),
    Link(mast_mcas, mast_subnet_router),
    Link(mast_subnet_router, None),
    Link(None, mast_subnet_router),
    Link(mast_mcas, None),
    Link(None, mast_mcas),
  ]

  client_subnet_config = yml_networks["client_net_mastodon"]["params"]

  client_up_latency = client_subnet_config["upstream"]["latency"]
  client_down_latency = client_subnet_config["downstream"]["latency"]

  client_up_loss = loss_specs[client_subnet_config["upstream"]["loss_profile"]]
  client_down_loss = loss_specs[client_subnet_config["downstream"]["loss_profile"]]

  for i in range(num_hcs_clients):
    links += [
      Link(client_nodes[f"mast_mcac_{i}"], None),
      Link(None, client_nodes[f"mast_mcac_{i}"]),

      Link(mast_subnet_router, client_nodes[f"mast_mcac_{i}"]),
      Link(client_nodes[f"mast_mcac_{i}"], mast_subnet_router),
    ]

  return (Topology(True, nodes, links), mast_server, client_addrs)


  # Addrs
  # eq ircClient4Addr = a(cl[4],hcs,irc,cl,1) .
  # eq ircClient4UserModelAddr = a(cl[4],hcs,irc,um,1) .
  # eq client4IfaceAddr = a(cl[4],hcs,irc,if,1) .
  # eq serverIface4Addr = a(srvN[4],hcs,irc,if,1) .
  # eq sendApp4Addr = a(cl[4],hcs,iod,app,1) .
  # eq iodineClient4Addr = a(cl[4],hcs,iod,cl,1) .
  # eq rcvApp4Addr = a(srvN[4],hcs,iod,app,1) .
  # eq serverIodineServer4Addr = a(srvN[4],hcs,iod,iodSrv,1) .
  # eq iodineClient4NetClientAddr = a(cl[4],tcp,iod,cl,1) .
  # eq iodineServer4NetServerAddr = a(srvN[4],tcp,iod,srv,1) .

  # Clients
  # eq ircClient4          = mkIrcClient-v2(ircClient4Addr, client4IfaceAddr, "Client4") .
  # eq ircClient4UserModel = mkIrcUMV2Actor(ircClient4UserModelAddr, "irc-test", ircClient4Addr) .
  # eq client4Iface        = mkIrcByteSeqIface(client4IfaceAddr, ircClient4Addr, sendApp4Addr) .
  # eq serverIface4        = mkIrcByteSeqIface(serverIface4Addr, ircServerAddr, rcvApp4Addr) .
  # eq sendApp4            = mkSendApp(sendApp4Addr, rcvApp4Addr, client4IfaceAddr, iodineClient4Addr) .
  # eq rcvApp4             = mkRcvApp(rcvApp4Addr, sendApp4Addr, serverIface4Addr, iodineClient4Addr) .
  # eq iodineClient4       = makeWClient(iodineClient4Addr, serverIodineServer4Addr, 'pwnd2 . 'com . root, a, 0.0) .
  # eq serverIodineServer4 = makeWNameServer(serverIodineServer4Addr, 0.0, zonePwnd2Com4) .
  # eq iodineClient4NetClient = makeNetClient(iodineClient4NetClientAddr, serverIodineServer4Addr, iodineClient4Addr, true, nullAddr, nullName) .
  # eq iodineServer4NetServer = makeNetServer(iodineServer4NetServerAddr, serverIodineServer4Addr) .
  # eq iodineMonitor       = mkWMonitor(iodineMonitorAddr) .

  # Links
  # aaa(serverIodineServer4Addr, iodineClient4Addr, LinkType-TCP-4stateLoss)
  # aaa(iodineClient4Addr, serverIodineServer4Addr, LinkType-TCP-4stateLoss) 


# def mk_iodine_topo(
#     yml_networks: Dict[Any, Any], 
#     yml_nodes: Dict[Any, Any],
#     yml_tgens: Dict[Any, Any],
#     loss_specs: Dict[str, Dict[str, float]],
#     irc_server: Node,
#     iod_monitor: Node,
#     subnet_idx: int,
# ) -> tuple[Topology, Node, list[Address]]:
#   """
#   See mk_mastodon_topo.
#   """

#   nodes = [].

#   # eq serverIface4Addr = a(srvN[4],hcs,irc,if,1) .
#   # eq rcvApp4Addr = a(srvN[4],hcs,iod,app,1) .
#   # eq serverIodineServer4Addr = a(srvN[4],hcs,iod,iodSrv,1) .
#   # eq iodineServer4NetServerAddr = a(srvN[4],tcp,iod,srv,1) .

#   # Create the static actor addresses (these are always basically the same, regardless of how many active hcs clients there are)
#   iod_server_iface_addr = Address("iod_server_iface_addr", f"a(srvN[{subnet_idx}],hcs,irc,if,1)")
#   iod_server_rcv_app_addr = Address("iod_server_rcv_app_addr", f"a(srvN[{subnet_idx}],hcs,iod,app,1)")
#   iod_server_addr = Address("iod_server_addr", f"a(srvN[{subnet_idx}],hcs,iod,iodSrv,1)")
#   iod_server_netserver_addr = Address("iod_server_netserver_addr", f"a(srvN[{subnet_idx}],tcp,iod,srv,1)")


#   iod_server_iface = Node(iod_server_iface_addr, "iod_server_iface", f"mkIrcByteSeqIface(serverIface4Addr, ircServerAddr, rcvApp4Addr) .")
#   iod_server_rcv_app = Node(iod_server_rcv_app_addr, "iod_server_rcv_app", f"mkRcvApp(rcvApp4Addr, sendApp4Addr, serverIface4Addr, iodineClient4Addr) .")
#   iod_server = Node(iod_server_addr, "iod_server", f"makeWNameServer(serverIodineServer4Addr, 0.0, zonePwnd2Com4) .")
#   iod_server_netserver = Node(iod_server_netserver_addr, "iod_server_netserver", f"makeNetServer(iodineServer4NetServerAddr, serverIodineServer4Addr) .")

#   # eq serverIface4        = mkIrcByteSeqIface(serverIface4Addr, ircServerAddr, rcvApp4Addr) .
#   # eq rcvApp4             = mkRcvApp(rcvApp4Addr, sendApp4Addr, serverIface4Addr, iodineClient4Addr) .
#   # eq serverIodineServer4 = makeWNameServer(serverIodineServer4Addr, 0.0, zonePwnd2Com4) .
#   # eq iodineServer4NetServer = makeNetServer(iodineServer4NetServerAddr, serverIodineServer4Addr) .

#   # eq iodineMonitor       = mkWMonitor(iodineMonitorAddr) .



#   # eq ircClient4Addr = a(cl[4],hcs,irc,cl,1) .
#   # eq ircClient4UserModelAddr = a(cl[4],hcs,irc,um,1) .
#   # eq client4IfaceAddr = a(cl[4],hcs,irc,if,1) .
#   # eq sendApp4Addr = a(cl[4],hcs,iod,app,1) .
#   # eq iodineClient4Addr = a(cl[4],hcs,iod,cl,1) .
#   # eq iodineClient4NetClientAddr = a(cl[4],tcp,iod,cl,1) 

#   # eq ircClient4          = mkIrcClient-v2(ircClient4Addr, client4IfaceAddr, "Client4") .
#   # eq ircClient4UserModel = mkIrcUMV2Actor(ircClient4UserModelAddr, "irc-test", ircClient4Addr) .
#   # eq client4Iface        = mkIrcByteSeqIface(client4IfaceAddr, ircClient4Addr, sendApp4Addr) .
#   # eq sendApp4            = mkSendApp(sendApp4Addr, rcvApp4Addr, client4IfaceAddr, iodineClient4Addr) .
#   # eq iodineClient4       = makeWClient(iodineClient4Addr, serverIodineServer4Addr, 'pwnd2 . 'com . root, a, 0.0) .
#   # eq iodineClient4NetClient = makeNetClient(iodineClient4NetClientAddr, serverIodineServer4Addr, iodineClient4Addr, true, nullAddr, nullName) .

#   # Create the actual static actors
#   mast_server_iface = Node(
#     mast_server_iface_addr, 
#     "mast_server_iface", 
#     f"mkIrcByteSeqIface({mast_server_iface_addr.name}, {irc_server.addr.name}, {mast_cmas_addr.name})")
#   mast_umas = Node(
#     mast_umas_addr,
#     "mast_umas",
#     f"mkUMactor({mast_umas_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmas_addr.name})")
#   mast_cmas = Node(
#     mast_cmas_addr,
#     "mast_cmas",
#     f'mkCMSndRcvActor({mast_cmas_addr.name}, {mast_edas_addr.name}, {mast_mcas_addr.name}, {mast_server_iface_addr.name}, "server5", "client5")')
#   mast_mcas = Node(
#     mast_mcas_addr,
#     "mast_mcas",
#     f"makeMastodonClient({mast_mcas_addr.name}, {mast_subnet_router_addr.name}, {mast_cmas_addr.name})")
#   mast_edas = Node(
#     mast_edas_addr,
#     "mast_edas",
#     f"makeDestiniActor({mast_edas_addr.name}, ed-iamges)")
#   mast_server = Node(
#     mast_server_addr,
#     "mast_server",
#     f"makeNetServer({mast_server_addr.name}, {mast_subnet_router_addr.name})")
#   mast_server_netclient = Node(
#     mast_server_netclient_addr,
#     "mast_server_netclient",
#     f"makeNetClient({mast_server_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcas_addr.name}, true, nullAddr, nullName)")
#   mast_subnet_router = Node(
#     mast_subnet_router_addr,
#     "mast_subnet_router",
#     f"makeMastodonServer({mast_subnet_router_addr.name})")

#   nodes += [mast_server_iface, mast_umas, mast_cmas, mast_mcas, mast_edas, mast_server, mast_server_netclient, mast_subnet_router]

#   hcs_config = yml_nodes["node_type_mastodon"]
#   num_hcs_clients = hcs_config["client_per_network"]["client_net_mastodon"]["quantity"]

#   client_nodes: dict[str, Node] = {}
#   client_addrs: list[Address] = []

#   for i in range(num_hcs_clients):
#     mast_client_addr = Address(f"mast_client_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,cl,{i})")
#     mast_client_user_model_addr = Address(f"mast_client_user_model_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,um,{i})")
#     mast_client_iface_addr = Address(f"mast_client_iface_addr_{i}", f"a(cl[{subnet_idx}],hcs,irc,if,{i})")
#     mast_umac_addr = Address(f"mast_umac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,um,{i})")
#     mast_cmac_addr = Address(f"mast_cmac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,cm,{i})")
#     mast_mcac_addr = Address(f"mast_mcac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,mc,{i})")
#     mast_edac_addr = Address(f"mast_edac_addr_{i}", f"a(cl[{subnet_idx}],hcs,mas,ed,{i})")
#     mast_client_netclient_addr = Address(f"mast_client_netclient_addr_{i}", f"a(cl[{subnet_idx}],tcp,mas,cl,{i})")
#     client_addrs.append(mast_client_addr)

#     named_nodes = {
#       f"mast_client_{i}": Node(
#         mast_client_addr, 
#         f"mast_client_{i}", 
#         f'mkIrcClient-v2({mast_client_addr.name}, {mast_client_iface_addr.name}, "Client{subnet_idx}")'),
      
#       f"mast_client_user_model_{i}": Node(
#         mast_client_user_model_addr, 
#         f"mast_client_user_model_{i}", 
#         f'mkIrcUMV2Actor({mast_client_user_model_addr.name}, "irc-test", {mast_client_addr.name})'),

#       f"mast_client_iface_{i}": Node(
#         mast_client_iface_addr, 
#         f"mast_client_iface_{i}", 
#         f"mkIrcByteSeqIface({mast_client_iface_addr.name}, {mast_client_addr.name}, {mast_cmac_addr.name})"),

#       f"mast_umac_{i}": Node(
#         mast_umac_addr, 
#         f"mast_umac_{i}", 
#         f"mkUMactor({mast_umac_addr.name}, mastodon-client-config-mastodon-bidi-ma, {mast_cmac_addr.name})"),

#       f"mast_cmac_{i}": Node(
#         mast_cmac_addr, 
#         f"mast_cmac_{i}", 
#         f'mkCMSndRcvActor({mast_cmac_addr.name}, {mast_edac_addr.name}, {mast_mcac_addr.name}, {mast_client_iface_addr.name}, "mast_client_{i}", "mast_server")'),

#       f"mast_mcac_{i}": Node(
#         mast_mcac_addr, 
#         f"mast_mcac_{i}", 
#         f"makeMastodonClient({mast_mcac_addr.name}, {mast_subnet_router_addr.name}, {mast_cmac_addr.name})"),

#       f"mast_edac_{i}": Node(
#         mast_edac_addr, 
#         f"mast_edac_{i}", 
#         f"makeDestiniActor({mast_edac_addr.name}, ed-images)"),

#       f"mast_client_netclient_{i}": Node(
#         mast_client_netclient_addr, 
#         f"mast_client_netclient_{i}", 
#         f"makeNetClient({mast_client_netclient_addr.name}, {mast_subnet_router_addr.name}, {mast_mcac_addr.name}, true, nullAddr, nullName)"),
#     }

#     nodes += named_nodes.values()
#     client_nodes.update(named_nodes)

#   server_subnet_config = yml_networks["mastodon_net"]["params"]
  
#   server_up_latency = server_subnet_config["upstream"]["latency"]
#   server_down_latency = server_subnet_config["downstream"]["latency"]

#   server_up_loss = loss_specs[server_subnet_config["upstream"]["loss_profile"]]
#   server_down_loss = loss_specs[server_subnet_config["downstream"]["loss_profile"]]

#   # TODO: give these the proper linktypes! Ask Christophe exactly how to combine probabilities
#   links = [
#     Link(mast_subnet_router, mast_mcas),
#     Link(mast_mcas, mast_subnet_router),
#     Link(mast_subnet_router, None),
#     Link(None, mast_subnet_router),
#     Link(mast_mcas, None),
#     Link(None, mast_mcas),
#   ]

#   client_subnet_config = yml_networks["client_net_mastodon"]["params"]

#   client_up_latency = client_subnet_config["upstream"]["latency"]
#   client_down_latency = client_subnet_config["downstream"]["latency"]

#   client_up_loss = loss_specs[client_subnet_config["upstream"]["loss_profile"]]
#   client_down_loss = loss_specs[client_subnet_config["downstream"]["loss_profile"]]

#   for i in range(num_hcs_clients):
#     links += [
#       Link(client_nodes[f"mast_mcac_{i}"], None),
#       Link(None, client_nodes[f"mast_mcac_{i}"]),

#       Link(mast_subnet_router, client_nodes[f"mast_mcac_{i}"]),
#       Link(client_nodes[f"mast_mcac_{i}"], mast_subnet_router),
#     ]

#   return (Topology(True, nodes, links), mast_server, client_addrs)