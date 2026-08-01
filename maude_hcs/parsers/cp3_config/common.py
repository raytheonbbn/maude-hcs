"""Basic classes and functions used by other cp3 config parsing functions"""

from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from enum import auto, Enum

from typing import Any

def default_loss() -> dict[str, float]:
  return {'p13': 0.0, 'p31': 0.0, 'p32': 0.0, 'p23': 0.0, 'p14': 0.0}

def profile_to_maude(prof: str) -> str:
  return "mastodon-config-influencer-4-ma" # TODO: fix this!!

def indent(i: int, lst: list[str]) -> list[str]:
    return [(" " * (i*4)) + line for line in lst]

# Note: any dataclass below with a name represents a maude variable *binding*, not just
# the maude value itself. In other words, it represents a maude object that should be bound
# to 'name' in the resulting maude file. Sometimes these objects may be used like plain maude values, however

class TGenType(Enum):
  MASTODON = "mas"
  DNS = "dns"
  FTP = "ftp"
  MINIO = "min"
  GORILLA = "gor"
  IRC = "irc"

  # TODO: what the heck are these?
  MASTODON_MONITOR = auto()
  MINIO_MONITOR = auto()

@dataclass_json
@dataclass(frozen=True)
class Address:
    name: str   # Variable name for this address in Maude
    maude: str  # Maude code to construct this address

@dataclass_json
@dataclass(frozen=True)
class Node:
  """Represents a Maude network actor"""
  addr: Address
  name: str
  maude: str

@dataclass_json
@dataclass(frozen=True, order=True)
class LinkType:
  """Represents qualities of a network link (loss transition probabilities and latency)"""
  prof: str
  p13: float = 0.0
  p31: float = 0.0
  p32: float = 0.0
  p23: float = 0.0
  p14: float = 0.0
  latency: float = 0.0

  @staticmethod
  def from_yml(prof, yml: dict[str, Any], latency: float = 0.0) -> "LinkType":
    return LinkType(prof, yml["p13"], yml["p31"], yml["p32"], yml["p23"], yml["p14"], latency)

  def name(self) -> str:
    return f"LinkType-{self.prof}-{int(self.latency * 1000)}"
  
  def maude(self) -> str:
    return (
      "(4stateLoss:"
      f"  (p13: {self.p13:.1f},"
      f"  p31: {self.p31:.1f},"
      f"  p32: {self.p32:.1f},"
      f"  p23: {self.p23:.1f},"
      f"  p14: {self.p14:.1f},"
      f"  oneWayDelay: {self.latency:.1f})"
      ")"
    )

  def combine(self, other: "LinkType") -> "LinkType":
    """Represents a (very) rough approximation of the linktype that would result from self followed by other"""
    return LinkType(
      prof=f"{self.prof}-{other.prof}",
      p13=max(self.p13, other.p13),
      p31=max(self.p31, other.p31),
      p32=max(self.p32, other.p32),
      p23=max(self.p23, other.p23),
      p14=max(self.p14, other.p14),
      latency=self.latency + other.latency,
    )

@dataclass_json
@dataclass(frozen=True)
class Link: 
  """Represents a network link between two Maude network actors"""
  src: Node | None  # if src is None, assumed to be ixp
  dst: Node | None  # ditto
  type: LinkType = field(default_factory = lambda: LinkType("perfect"))

  def has_same_endpoints(self, other: "Link") -> bool:
    return self.src == other.src and self.dst == other.dst

  def is_similar_to(self, other: "Link") -> bool:
      return self.type == other.type

  def maude(self) -> str:
    return f"aaa({self.src.addr.name if self.src else "IXP-DEFAULT-ADDR"}, {self.dst.addr.name if self.dst else "IXP-DEFAULT-ADDR"}, {self.type.name()})"

class Counter:
  """A counter that returns and increments the current count each time its called"""
  def __init__(self, start: int):
    self.i = start

  def __call__(self) -> int:
    result = self.i
    self.i += 1
    return result

@dataclass_json
@dataclass(frozen=True)
class TGenConfig:
  profile: str
  uplink: LinkType
  downlink: LinkType

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