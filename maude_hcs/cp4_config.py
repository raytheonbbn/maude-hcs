"""Validated CP4 reference-architecture configuration and fault schedules.

Channel aliases are normalized for the Maude libraries.  Actor numbering follows
YAML insertion order; the reference testbed uses that same order for its servers
and six client groups.  Network delays are directional and expressed in seconds
only when queried through :meth:`Cp4Config.one_way_delay`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Mapping

import yaml


class Cp4ConfigError(ValueError):
    """A configuration cannot be represented by the CP4 generator."""


CHANNEL_ALIASES = {"obfs": "obfs4", "racetunnel": "webtunnel"}
CHANNELS = {"obfs4", "webtunnel", "skyhook", "mastodon", "iodine", "direct"}
MODEL_PARAMETERS = {"user_model", "user_model_client", "user_model_server"}
CHANNEL_PARAMETERS = {
    "obfs4": {"iat_mode"},
    "webtunnel": {"port", "tls_name", "upgrade_path"},
    "iodine": {"max_query_length", "max_response_size"},
    "skyhook": MODEL_PARAMETERS | {"fetch_bucket", "post_bucket", "initial_fetch_uuid", "post_uuid", "open_objects"},
    "mastodon": MODEL_PARAMETERS | {"username", "hashtag_send", "hashtag_recv"},
    "direct": set(),
}


@dataclass(frozen=True)
class NetworkConfig:
    name: str
    kind: str
    nat: bool
    upstream_ms: float
    downstream_ms: float


@dataclass(frozen=True)
class ChannelConfig:
    type: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ServerConfig:
    name: str
    network: str
    client_channels: dict[str, ChannelConfig]


@dataclass(frozen=True)
class ServerLink:
    server_a: str
    server_b: str
    channel: ChannelConfig


@dataclass(frozen=True)
class ClientConnection:
    server: str
    direction: str
    channel: ChannelConfig


@dataclass(frozen=True)
class ClientConfig:
    index: int
    name: str
    node_type: str
    network: str
    profile: str
    primary: ClientConnection
    backup: ClientConnection | None

    @property
    def connections(self) -> tuple[ClientConnection, ...]:
        return (self.primary,) if self.backup is None else (self.primary, self.backup)


@dataclass(frozen=True)
class Cp4Config:
    env: str
    conversation_duration: float
    max_start_delay: float
    one_way_availability: float
    analysis_window_size: float
    input_seed: int
    networks: dict[str, NetworkConfig]
    servers: dict[str, ServerConfig]
    links: tuple[ServerLink, ...]
    clients: tuple[ClientConfig, ...]
    user_models_dir: Path
    source_path: Path | None
    tgen: dict[str, Any] = field(default_factory=dict)
    adversary: dict[str, Any] = field(default_factory=dict)

    def one_way_delay(self, source_network: str, destination_network: str) -> float:
        """Delay through the source upstream and destination downstream routers."""
        return (self.networks[source_network].upstream_ms
                + self.networks[destination_network].downstream_ms) / 1000.0

    def profile_path(self, channel: str, name: str) -> Path:
        """Resolve the reference testbed's ``user_models/<channel>`` assets."""
        filename = Path(name)
        if not filename.suffix:
            filename = filename.with_suffix(".json")
        if filename.is_absolute():
            return filename
        aliases = {"obfs4": "obfs", "webtunnel": "racetunnel"}
        directory = self.user_models_dir / aliases.get(channel, channel)
        return directory / filename

    def required_profiles(self) -> tuple[Path, ...]:
        paths = [self.profile_path("irc", client.profile) for client in self.clients]
        channels = [channel for server in self.servers.values()
                    for channel in server.client_channels.values()]
        channels += [link.channel for link in self.links]
        channels += [connection.channel for client in self.clients
                     for connection in client.connections]
        for channel in channels:
            for key in ("user_model", "user_model_client", "user_model_server"):
                if key in channel.config:
                    paths.append(self.profile_path(channel.type, channel.config[key]))
        return tuple(dict.fromkeys(paths))

    def profile_rooms(self, profile: str) -> tuple[str, ...]:
        return load_profile_rooms(self.profile_path("irc", profile))


@dataclass(frozen=True)
class FaultEvent:
    time: float
    action: str
    network_a: str
    network_b: str


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise Cp4ConfigError(f"{location} must be a mapping with string keys")
    return value


def _keys(value: Mapping[str, Any], allowed: set[str], location: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise Cp4ConfigError(f"{location}: unsupported field(s): {', '.join(sorted(unknown))}")


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Cp4ConfigError(f"{location} must be a nonempty string")
    return value


def _number(value: Any, location: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Cp4ConfigError(f"{location} must be a number")
    result = float(value)
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        constraint = "positive" if positive else "nonnegative"
        raise Cp4ConfigError(f"{location} must be finite and {constraint}")
    return result


def _integer(value: Any, location: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Cp4ConfigError(f"{location} must be an integer")
    if positive and value <= 0:
        raise Cp4ConfigError(f"{location} must be positive")
    return value


def _channel(value: Any, location: str) -> ChannelConfig:
    data = _mapping(value, location)
    _keys(data, {"type", "config"}, location)
    name = _string(data.get("type"), f"{location}.type")
    name = CHANNEL_ALIASES.get(name, name)
    if name not in CHANNELS:
        raise Cp4ConfigError(f"{location}.type: unsupported channel {name!r}")
    parameters = dict(_mapping(data.get("config") or {}, f"{location}.config"))
    _keys(parameters, CHANNEL_PARAMETERS[name], f"{location}.config")
    for key in MODEL_PARAMETERS | {"tls_name", "upgrade_path", "fetch_bucket", "post_bucket",
                                  "initial_fetch_uuid", "post_uuid", "username", "hashtag_send", "hashtag_recv"}:
        if key in parameters:
            _string(parameters[key], f"{location}.config.{key}")
    if "iat_mode" in parameters:
        mode = _integer(parameters["iat_mode"], f"{location}.config.iat_mode")
        if mode not in (0, 1, 2):
            raise Cp4ConfigError(f"{location}.config.iat_mode must be 0, 1, or 2")
    for key in ("max_query_length", "max_response_size", "port", "open_objects"):
        if key in parameters:
            _integer(parameters[key], f"{location}.config.{key}", positive=True)
    return ChannelConfig(name, parameters)


def _profiles(value: Any, quantity: int, location: str) -> list[str]:
    """Assign profile fractions deterministically using largest remainders."""
    data = _mapping(value, location)
    if not data:
        raise Cp4ConfigError(f"{location} must contain at least one profile")
    weights = [_number(weight, f"{location}.{name}") for name, weight in data.items()]
    if not math.isclose(sum(weights), 1.0, rel_tol=0, abs_tol=1e-6):
        raise Cp4ConfigError(f"{location} profile fractions must sum to 1")
    expected = [quantity * weight for weight in weights]
    counts = [math.floor(count) for count in expected]
    order = sorted(range(len(counts)), key=lambda i: -(expected[i] - counts[i]))
    for index in order[:quantity - sum(counts)]:
        counts[index] += 1
    return [name for name, count in zip(data, counts) for _ in range(count)]


def parse_cp4_config(
    value: Mapping[str, Any], *, source_path: str | Path | None = None,
    user_models_dir: str | Path | None = None, seed: int | None = None,
    check_assets: bool = False,
) -> Cp4Config:
    """Parse the CP4 YAML shape without mutating it.

    Acyclic server links are required because the IRC relay model forwards along
    a tree.  Disconnected server components are allowed.  Multiple clients and
    profile fractions are expanded in insertion order (the current external
    runner only generates an IRC input for the first profile in each node group).
    """
    data = _mapping(value, "configuration")
    _keys(data, {"env", "conversation_duration", "max_start_delay", "one_way_availability",
                 "analysis_window_size", "input_seed", "network", "irc_servers", "nodes",
                 "tgen", "adversary"}, "configuration")
    for section in ("tgen", "adversary"):
        if _mapping(data.get(section) or {}, section):
            raise Cp4ConfigError(f"nonempty {section} is not supported by the CP4 generator")
    source = Path(source_path).resolve() if source_path is not None else None
    models = (Path(user_models_dir).resolve() if user_models_dir is not None
              else (source.parent if source else Path.cwd()) / "user_models")
    networks: dict[str, NetworkConfig] = {}
    for name, raw in _mapping(data.get("network"), "network").items():
        location = f"network.{name}"
        item = _mapping(raw, location)
        _keys(item, {"network", "nat", "params"}, location)
        nat = item.get("nat", False)
        if not isinstance(nat, bool):
            raise Cp4ConfigError(f"{location}.nat must be a boolean")
        parameters = _mapping(item.get("params"), f"{location}.params")
        _keys(parameters, {"upstream", "downstream"}, f"{location}.params")
        delays = []
        for direction in ("upstream", "downstream"):
            path = f"{location}.params.{direction}"
            spec = _mapping(parameters.get(direction), path)
            _keys(spec, {"latency_ms"}, path)
            delays.append(_number(spec.get("latency_ms"), f"{path}.latency_ms"))
        networks[name] = NetworkConfig(name, _string(item.get("network"), f"{location}.network"),
                                       nat, *delays)
    if not networks:
        raise Cp4ConfigError("network must contain at least one network")

    irc_servers = _mapping(data.get("irc_servers"), "irc_servers")
    _keys(irc_servers, {"servers", "topology"}, "irc_servers")
    servers: dict[str, ServerConfig] = {}
    for name, raw in _mapping(irc_servers.get("servers"), "irc_servers.servers").items():
        location = f"irc_servers.servers.{name}"
        item = _mapping(raw, location)
        _keys(item, {"network", "client_channels"}, location)
        network = _string(item.get("network"), f"{location}.network")
        if network not in networks:
            raise Cp4ConfigError(f"{location}: unknown network {network!r}")
        channels = {}
        for name_, parameters in _mapping(item.get("client_channels") or {},
                                         f"{location}.client_channels").items():
            channel = _channel({"type": name_, "config": parameters},
                               f"{location}.client_channels.{name_}")
            if channel.type in channels:
                raise Cp4ConfigError(f"{location}: duplicate channel alias {name_!r}")
            channels[channel.type] = channel
        servers[name] = ServerConfig(name, network, channels)
    if not servers:
        raise Cp4ConfigError("irc_servers.servers must contain at least one server")

    topology = irc_servers.get("topology") or []
    if not isinstance(topology, list):
        raise Cp4ConfigError("irc_servers.topology must be a list")
    links = []
    components = {name: name for name in servers}
    for index, raw in enumerate(topology):
        location = f"irc_servers.topology[{index}]"
        item = _mapping(raw, location)
        _keys(item, {"server_a", "server_b", "channel"}, location)
        a, b = item.get("server_a"), item.get("server_b")
        for key, name in (("server_a", a), ("server_b", b)):
            _string(name, f"{location}.{key}")
            if name not in servers:
                raise Cp4ConfigError(f"{location}.{key}: unknown server {name!r}")
        if components[a] == components[b]:
            raise Cp4ConfigError(f"{location}: server topology must be acyclic (no duplicate/self links)")
        old, new = components[b], components[a]
        components = {name: new if component == old else component
                      for name, component in components.items()}
        links.append(ServerLink(a, b, _channel(item.get("channel"), f"{location}.channel")))

    clients = []
    for node_type, raw in _mapping(data.get("nodes"), "nodes").items():
        location = f"nodes.{node_type}"
        item = _mapping(raw, location)
        _keys(item, {"channel_config", "client_per_network"}, location)
        connection_data = _mapping(item.get("channel_config"), f"{location}.channel_config")
        _keys(connection_data, {"primary", "backup"}, f"{location}.channel_config")
        connections = {}
        for role in ("primary", "backup"):
            if role == "backup" and role not in connection_data:
                continue
            path = f"{location}.channel_config.{role}"
            connection = _mapping(connection_data.get(role), path)
            _keys(connection, {"server", "direction", "channel"}, path)
            server = _string(connection.get("server"), f"{path}.server")
            if server not in servers:
                raise Cp4ConfigError(f"{path}: unknown server {server!r}")
            direction = connection.get("direction", "bidirectional")
            if direction != "bidirectional":
                raise Cp4ConfigError(f"{path}.direction must be bidirectional for IRC")
            channel = _channel(connection.get("channel"), f"{path}.channel")
            if channel.type != "direct" and channel.type not in servers[server].client_channels:
                raise Cp4ConfigError(f"{path}: server {server!r} has no {channel.type!r} client channel")
            connections[role] = ClientConnection(server, direction, channel)
        populations = _mapping(item.get("client_per_network"), f"{location}.client_per_network")
        if not populations:
            raise Cp4ConfigError(f"{location}.client_per_network must not be empty")
        for network, population in populations.items():
            path = f"{location}.client_per_network.{network}"
            if network not in networks:
                raise Cp4ConfigError(f"{path}: unknown network {network!r}")
            group = _mapping(population, path)
            _keys(group, {"quantity", "profiles"}, path)
            quantity = _integer(group.get("quantity", 1), f"{path}.quantity", positive=True)
            for profile in _profiles(group.get("profiles"), quantity, f"{path}.profiles"):
                index = len(clients) + 1
                clients.append(ClientConfig(index, f"alice{index}", node_type, network, profile,
                                            connections["primary"], connections.get("backup")))
    if not clients:
        raise Cp4ConfigError("nodes must contain at least one client")
    input_seed = _integer(data.get("input_seed", 1234) if seed is None else seed, "input_seed")
    if input_seed < 0:
        raise Cp4ConfigError("input_seed must be nonnegative (the Maude random counter is a Nat)")
    result = Cp4Config(
        env=_string(data.get("env", "cp4"), "env"),
        conversation_duration=_number(data.get("conversation_duration"), "conversation_duration", positive=True),
        max_start_delay=_number(data.get("max_start_delay", 900), "max_start_delay"),
        one_way_availability=_number(data.get("one_way_availability", 30), "one_way_availability", positive=True),
        analysis_window_size=_number(data.get("analysis_window_size", 300), "analysis_window_size", positive=True),
        input_seed=input_seed,
        networks=networks, servers=servers, links=tuple(links), clients=tuple(clients),
        user_models_dir=models, source_path=source,
    )
    if check_assets:
        missing = [str(path) for path in result.required_profiles() if not path.is_file()]
        if missing:
            raise Cp4ConfigError("missing user model(s): " + ", ".join(missing))
    return result


def load_cp4_config(path: str | Path, *, user_models_dir: str | Path | None = None,
                    seed: int | None = None, check_assets: bool = True) -> Cp4Config:
    source = Path(path)
    with source.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    return parse_cp4_config(value, source_path=source, user_models_dir=user_models_dir,
                            seed=seed, check_assets=check_assets)


def parse_fault_schedule(value: Any, config: Cp4Config) -> tuple[FaultEvent, ...]:
    """Compile runner actions: each disconnect/reconnect precedes its sleep."""
    data = _mapping(value, "fault schedule")
    _keys(data, {"actions"}, "fault schedule")
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise Cp4ConfigError("fault schedule.actions must be a list")
    events = []
    elapsed = 0.0
    for index, raw in enumerate(actions):
        location = f"fault schedule.actions[{index}]"
        item = _mapping(raw, location)
        action = item.get("action")
        if action == "sleep":
            _keys(item, {"action", "sleep"}, location)
        elif action in ("disconnect", "reconnect"):
            _keys(item, {"action", "net_1", "net_2", "sleep"}, location)
            a, b = item.get("net_1"), item.get("net_2")
            for key, network in (("net_1", a), ("net_2", b)):
                _string(network, f"{location}.{key}")
                if network not in config.networks:
                    raise Cp4ConfigError(f"{location}.{key}: unknown network {network!r}")
            if a == b:
                raise Cp4ConfigError(f"{location}: fault endpoints must be different networks")
            events.append(FaultEvent(elapsed, action, a, b))
        else:
            raise Cp4ConfigError(f"{location}: unsupported action {action!r}")
        elapsed += _number(item.get("sleep", 0), f"{location}.sleep")
    return tuple(events)


def load_fault_schedule(path: str | Path, config: Cp4Config) -> tuple[FaultEvent, ...]:
    with Path(path).open(encoding="utf-8") as stream:
        return parse_fault_schedule(yaml.safe_load(stream), config)


def load_profile_rooms(path: str | Path) -> tuple[str, ...]:
    """Find the rooms declared by IRC set_room_numbers actions, in file order."""
    with Path(path).open(encoding="utf-8") as stream:
        model = json.load(stream)
    rooms: dict[str, None] = {}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            if value.get("type") == "set_room_numbers":
                declared = _mapping(value.get("rooms"), f"{path}: set_room_numbers.rooms")
                for room in declared:
                    _string(room, f"{path}: room name")
                    if not room.startswith("#"):
                        raise Cp4ConfigError(f"{path}: IRC channel names must begin with #")
                    rooms[room] = None
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(model)
    if not rooms:
        raise Cp4ConfigError(f"{path}: no set_room_numbers rooms found")
    return tuple(rooms)
