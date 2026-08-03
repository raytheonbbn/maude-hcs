"""Basic classes and functions used by other cp3 config parsing functions"""

from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from enum import auto, Enum
from collections.abc import Sequence

from typing import Any

def default_loss() -> dict[str, float]:
  return {'p13': 0.0, 'p31': 0.0, 'p32': 0.0, 'p23': 0.0, 'p14': 0.0}

def profile_to_maude(profile: str) -> str:
    mapping = {
        "irc-irc-10": "irc-irc-10-ma-v2",
        "irc-irc-11": "irc-irc-11-ma-v2",
        "irc-irc-2": "irc-irc-2-ma-v2",
        "irc-irc-3": "irc-irc-3-ma-v2",
        "irc-irc-6": "irc-irc-6-ma-v2",
        "irc-irc-7": "irc-irc-7-ma-v2",
        "irc-tgen-irc-11": "irc-tgen-irc-11-ma-v2",
        "irc-tgen-irc-12": "irc-tgen-irc-12-ma-v2",
        "irc-tgen-irc-2": "irc-tgen-irc-2-ma-v2",
        "irc-tgen-irc-4": "irc-tgen-irc-4-ma-v2",
        "irc-tgen-irc-5": "irc-tgen-irc-5-ma-v2",
        "irc-tgen-irc-6": "irc-tgen-irc-6-ma-v2",
        "irc-tgen-irc-7": "irc-tgen-irc-7-ma-v2",
        "irc-tgen-irc-8": "irc-tgen-irc-8-ma-v2",
        "irc-tgen-irc-9": "irc-tgen-irc-9-ma-v2",
        "ftp-tgen-fast": "ftp-tgen-fast-ma-v2",
        "ftp-tgen-medium": "ftp-tgen-medium-ma-v2",
        "ftp-tgen-slow": "ftp-tgen-slow-ma-v2",
        "minio-tgen-fast": "minio-tgen-fast-ma-v2",
        "minio-tgen-medium": "minio-tgen-medium-ma-v2",
        "minio-tgen-slow": "minio-tgen-slow-ma-v2",
        "gorilla-tgen-irc-1": "gorilla-tgen-irc-1-ma-v2",
        "gorilla-tgen-irc-10": "gorilla-tgen-irc-10-ma-v2",
        "gorilla-tgen-irc-11": "gorilla-tgen-irc-11-ma-v2",
        "gorilla-tgen-irc-12": "gorilla-tgen-irc-12-ma-v2",
        "gorilla-tgen-irc-2": "gorilla-tgen-irc-2-ma-v2",
        "gorilla-tgen-irc-3": "gorilla-tgen-irc-3-ma-v2",
        "gorilla-tgen-irc-4": "gorilla-tgen-irc-4-ma-v2",
        "gorilla-tgen-irc-5": "gorilla-tgen-irc-5-ma-v2",
        "gorilla-tgen-irc-6": "gorilla-tgen-irc-6-ma-v2",
        "gorilla-tgen-irc-7": "gorilla-tgen-irc-7-ma-v2",
        "gorilla-tgen-irc-8": "gorilla-tgen-irc-8-ma-v2",
        "gorilla-tgen-irc-9": "gorilla-tgen-irc-9-ma-v2",
    }
    return mapping.get(profile, profile)

def indent_all(lst: list[str], indent=1) -> list[str]:
    return [(" " * (indent*4)) + line for line in lst]

def indented_lines(*args):
  return Lines(*args, indent=1)

# Note: any dataclass below with a name represents a maude variable *binding*, not just
# the maude value itself. In other words, it represents a maude object that should be bound
# to 'name' in the resulting maude file. Sometimes these objects may be used like plain maude values, however

class Lines:
  def __init__(self, *args, indent=0):
    lines = []
    for arg in args:
      if isinstance(arg, Lines):
        lines += arg.lines
      else:
        lines += [str(arg)]
    self.lines = indent_all(lines, indent=indent)

  def join(self, other):
    return Lines(*(self.lines + other.lines))

  def indent(self, indent=1):
    return Lines(*self.lines, indent=indent)

class InsertType(Enum):
  DECL = auto()
  BIND = auto()

@dataclass_json
@dataclass(frozen=True, order=True)
class Insert:
  typ: InsertType
  lines: Lines

def pairs_to_names_and_binds(
    tups: Sequence[tuple[str, str | Lines] | Insert],
) -> tuple[Lines, Lines]:
  
  decl_lines = []
  bind_lines = []

  for x in tups:
    if isinstance(x, Insert):
      if x.typ == InsertType.DECL:
        decl_lines.append(x.lines)
      else:
        bind_lines.append(x.lines)
    else:
      decl_lines.append(x[0])
      if isinstance(x[1], Lines):
        bind_lines.append(f"eq {x[0]}:")
        bind_lines += x[1].indent().lines
        bind_lines += "."
      else:
        bind_lines.append(f"eq {x[0]}: {x[1]} .")
  return (Lines(*decl_lines), Lines(*bind_lines))

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
@dataclass(frozen=True, order=True)
class LinkType:
  """Represents qualities of a network link (loss transition probabilities and latency)"""
  profile: str
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
    return f"LinkType-{self.profile}-{int(self.latency * 1000)}"
  
  def maude(self) -> str:
    return (
      "(4stateLoss:"
      f" (p13: {self.p13:.1f},"
      f" p31: {self.p31:.1f},"
      f" p32: {self.p32:.1f},"
      f" p23: {self.p23:.1f},"
      f" p14: {self.p14:.1f},"
      f" oneWayDelay: {self.latency:.1f})"
      ")"
    )

  def combine(self, other: "LinkType") -> "LinkType":
    """Represents a (very) rough approximation of the linktype that would result from self followed by other"""
    return LinkType(
      profile=f"{self.profile}-{other.profile}",
      p13=max(self.p13, other.p13),
      p31=max(self.p31, other.p31),
      p32=max(self.p32, other.p32),
      p23=max(self.p23, other.p23),
      p14=max(self.p14, other.p14),
      latency=self.latency + other.latency,
    )

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
  client_subnet_name: str # Only used for comments
  client_subnet_idx: int
  client_subnet_dns: str
  uplink: LinkType
  downlink: LinkType

@dataclass_json
@dataclass(frozen=True, order=True)
class Cp3ConfigChunk:
  """A chunk of the final maude configuration that can be easily combined with other chunks from
  e.g. protocol parsing functions.
  """

  images: Lines = field(default_factory=Lines)
  model_map: Lines = field(default_factory=Lines)
  zones: Lines = field(default_factory=Lines)
  resolver_cache: Lines = field(default_factory=Lines)
  addr_decls: Lines = field(default_factory=Lines)
  addr_binds: Lines = field(default_factory=Lines)
  transports: Lines = field(default_factory=Lines)
  linktype_decls: Lines = field(default_factory=Lines)
  linktype_binds: Lines = field(default_factory=Lines)
  linkdata: Lines = field(default_factory=Lines)
  actor_decls: Lines = field(default_factory=Lines)
  actor_binds: Lines = field(default_factory=Lines)
  init_actors: Lines = field(default_factory=Lines)
  init_msgs: Lines = field(default_factory=Lines)
  client_addrs: Lines = field(default_factory=Lines)

  # def __post_init__(self):
  #   assert set(self.addr_binds.keys()).issubset(self.addr_decls)
  #   assert set(self.actor_binds.keys()).issubset(self.actor_decls)
  #   assert set(self.linktype_binds.keys()).issubset(self.linktype_names)

  def join(self, other: "Cp3ConfigChunk") -> "Cp3ConfigChunk":

    return Cp3ConfigChunk(
      images=self.images.join(other.images),
      model_map=self.model_map.join(other.model_map),
      zones=self.zones.join(other.zones),
      resolver_cache=self.resolver_cache.join(other.resolver_cache),
      addr_decls=self.addr_decls.join(other.addr_decls),
      addr_binds=self.addr_binds.join(other.addr_binds),
      transports=self.transports.join(other.transports),
      linktype_decls=self.linktype_decls.join(other.linktype_decls),
      linktype_binds=self.linktype_binds.join(other.linktype_binds),
      linkdata=self.linkdata.join(other.linkdata),
      actor_decls=self.actor_decls.join(other.actor_decls),
      actor_binds=self.actor_binds.join(other.actor_binds),
      init_actors=self.init_actors.join(other.init_actors),
      init_msgs=self.init_msgs.join(other.init_msgs),
      client_addrs=self.client_addrs.join(other.client_addrs),
    )