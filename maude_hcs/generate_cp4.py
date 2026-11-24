"""Generate executable CP4 IRC/HCS experiments from reference-architecture YAML.

Run ``python -m maude_hcs.generate_cp4 CONFIG --outDir OUTPUT``.  Each client
connection and server edge owns a separate bidirectional HCS and IRC endpoint.
The generator uses the existing protocol models, including their queues,
polling and TCP/DNS behavior; it does not replace hidden channels with delays.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random
import re
from typing import Any

from .cp4_config import Cp4Config, Cp4ConfigError, load_cp4_config
from .cp4_channels import ChannelEmission, emit_channel
from .convert_markov_json_to_maude_v1 import JsonToMaudeParser
from .convert_markov_json_to_maude_v2 import MarkovJsonToMaudeConverter


LIB = Path(__file__).resolve().parent / "lib"


def quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def number(value: float) -> str:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise Cp4ConfigError("times must be finite and nonnegative")
    return repr(value)


@dataclass(frozen=True)
class GeneratedExperiment:
    scenario: Path
    runner: Path
    manifest: Path


@dataclass(frozen=True)
class ActorDefinition:
    name: str
    expression: str
    description: str


class ModelLibrary:
    def __init__(self, config: Cp4Config):
        self.config = config
        self.models: dict[tuple[str, Path], tuple[str, str, str]] = {}
        self.files: dict[str, str] = {}
        self.irc_map: dict[str, str] = {}
        self.catalog: dict[str, dict[str, str]] = {}
        self._stems: set[str] = set()

    def add(self, kind: str, filename: str) -> tuple[str, str, str]:
        path = self.config.profile_path(kind, filename).resolve()
        key = kind, path
        if key not in self.models:
            data = json.loads(path.read_text())
            # Maude treats underscores as argument slots. Use safe, readable
            # identifiers while keeping distinct paths/case variants separate.
            label = re.sub(r"[^A-Za-z0-9]+", "-", path.stem).strip("-").lower() or "model"
            base = f"cp4-{kind}-{label}"
            stem, suffix = base, 2
            while stem in self._stems:
                stem, suffix = f"{base}-{suffix}", suffix + 1
            self._stems.add(stem)
            target = f"models/{stem}.maude"
            if kind == "irc":
                if not data.get("states"):
                    raise Cp4ConfigError(f"IRC profile {path} must be a v2 model with states")
                # Runtime workload stops at the experiment horizon; profile step
                # limits still apply. All inputs go through cp4Input(client).
                parser = MarkovJsonToMaudeConverter(stem, stem)
                module, op = stem.upper() + "-MAMODEL-V2", stem + "-ma-v2"
                self.irc_map[stem] = op
            else:
                actions, markov = data.get("actions"), data.get("markov")
                if not actions or not markov or set(actions) != set(markov):
                    raise Cp4ConfigError(f"HCS profile {path} must have matching actions and Markov states")
                if any(set(transitions) - set(markov) for transitions in markov.values()):
                    raise Cp4ConfigError(f"HCS profile {path} references an unknown Markov state")
                # Testbed TgenBase defaults to the first action. The v1
                # Maude actor reads the action's start flag, not parameters.start.
                starts = [state for state, action in actions.items() if action.get("start")]
                if len(starts) > 1:
                    raise Cp4ConfigError(f"HCS profile {path} has multiple start states")
                start = starts[0] if starts else next(iter(actions))
                if start not in actions:
                    raise Cp4ConfigError(f"HCS profile {path} has an unknown start state: {start}")
                actions[start]["start"] = True
                for state, action in list(actions.items()):
                    if kind == "mastodon":
                        action["type"] = {"post": "media", "fetch": "download"}.get(action.get("type"), action.get("type"))
                    # Testbed sleeps after an action completes. The existing UM
                    # implements waits as states, so insert one without consuming
                    # an extra model step. Existing explicit waits are preserved.
                    if "sleep" in action and action.get("type") != "wait":
                        wait = f"cp4_wait_after_{state}"
                        while wait in actions:
                            wait += "_"
                        actions[wait] = {"type": "wait", "sleep": action.pop("sleep"),
                                         "cp4_internal_wait": True}
                        markov[wait] = markov[state]
                        markov[state] = {wait: 1.0}
                parser = JsonToMaudeParser(stem, stem)
                module, op = stem.upper() + "-MAMODEL", stem + "-ma"
            self.files[target] = (f"--- User model source: {quoted(str(path))}.\n"
                                  + parser.generate(json.dumps(data)))
            normalized = target.removesuffix(".maude") + ".json"
            self.files[normalized] = json.dumps(data, indent=2) + "\n"
            self.models[key] = target, module, op
            self.catalog[op] = dict(kind=kind, source=str(path), generated_file=target,
                                   normalized_json=normalized, module=module, operator=op)
            if kind == "irc":
                self.catalog[op]["key"] = stem
        return self.models[key]

    def channel_models(self, kind: str, cfg: dict, server_cfg: dict) -> tuple[str, str]:
        if kind not in {"mastodon", "skyhook"}:
            return "", ""
        client = cfg.get("user_model_client", cfg.get("user_model"))
        server = cfg.get("user_model_server", server_cfg.get("user_model_server", server_cfg.get("user_model")))
        if not client or not server:
            raise Cp4ConfigError(f"{kind} requires client and server user_model configuration")
        return self.add(kind, client)[2], self.add(kind, server)[2]


def _csv_workload(path: Path) -> tuple[list[str], list[tuple[float, str, str]]]:
    with path.open(newline="") as source:
        rows = csv.reader(source)
        rooms = next(rows, [])
        if not rooms or any(not room.startswith("#") for room in rooms):
            raise Cp4ConfigError(f"{path}: first CSV row must list IRC channels")
        events = []
        previous = 0.0
        for line, row in enumerate(rows, 2):
            if not row:
                continue
            if len(row) != 3:
                raise Cp4ConfigError(f"{path}:{line}: expected time,channel,message")
            time = float(row[0])
            number(time)
            if time < previous or row[1] not in rooms:
                raise Cp4ConfigError(f"{path}:{line}: unordered time or undeclared channel")
            events.append((time, row[1], row[2]))
            previous = time
    return rooms, events


def _network(config: Cp4Config, channels: list[ChannelEmission], addresses: set[str]) -> tuple[list[str], list[str], list[ActorDefinition]]:
    """TCP uses per-router directional netem delays; iodine uses DNS links."""
    endpoints: dict[str, str] = {}
    services = set().union(*(c.shared_services for c in channels)) if channels else set()
    for channel in channels:
        endpoints.update(channel.network_endpoints)
    # Public cover services have no additional netem hop in the reference YAML.
    # Configurations can explicitly place them on named service networks.
    for kind, service, network in (("s3", "s3SrvAddr", "minio_net"), ("mastodon", "masSrvAddr", "mastodon_net")):
        if kind in services:
            endpoints[service] = network if network in config.networks else ""
    addresses.update(endpoints)
    addresses.update({"transportAddr", "observerAddr", "dnsAddr"})
    policy = ["mod CP4-NETWORK-POLICY is", "  inc TRANSPORT .", "  inc CP4-ADDRESSES .",
              "  var CP4CONNECTIONID : Nat ."]
    for addr in endpoints:
        policy.append(f"  eq transport({addr}, CP4CONNECTIONID) = tcppersist({addr}, CP4CONNECTIONID) .")
    policy.append("endm")
    equations = []
    links = []
    dns_networks = [net for net in config.networks.values() if net.kind == "dns"]
    if len(dns_networks) > 1 and any(channel.network_links for channel in channels):
        raise Cp4ConfigError("Iodine generation requires at most one DNS resolver network")
    dns_network = dns_networks[0] if dns_networks else None
    for index, network in enumerate([*config.networks, ""], 1):
        net = config.networks.get(network)
        up = net.upstream_ms / 1000 if net else 0.0
        down = net.downstream_ms / 1000 if net else 0.0
        for suffix, delay in (("Up", up), ("Down", down)):
            equations += [f"op net{index}{suffix} : -> AttributeSet .",
                          f"eq net{index}{suffix} = (oneWayDelay: {number(delay)}, dropP: 0.0, canDrop: false) ."]
        for addr, attached in endpoints.items():
            if attached == network:
                links += [f"aaa({addr}, IXP-DEFAULT-ADDR, net{index}Up)",
                          f"aaa(IXP-DEFAULT-ADDR, {addr}, net{index}Down)"]
    for index, channel in enumerate(channels, 1):
        for hop, (left, right, left_net, right_net) in enumerate(channel.network_links):
            for label, src, dst, a, b in (("Up", left, right, left_net, right_net),
                                         ("Down", right, left, right_net, left_net)):
                attr = f"dnsLink{index}Hop{hop}{label}"
                seconds = config.one_way_delay(a, b)
                # Collapse the testbed's corporate forwarder -> public resolver
                # -> iodine authority path while retaining both resolver hops.
                if dns_network and dns_network.name not in (a, b):
                    seconds += (dns_network.upstream_ms + dns_network.downstream_ms) / 1000
                delay = number(seconds)
                equations += [f"op {attr} : -> AttributeSet .",
                    f'eq {attr} = (delayType: "Constant", delayConst: {delay}, delayMean: {delay}, '
                    f'delayStd: 0.0, noiseMin: 0.0, noiseMax: 0.00001, oneWayDelay: {delay}, dropP: 0.0, canDrop: false) .']
                links.append(f"aaa({src}, {dst}, {attr})")
    if links:
        equations.append("eq LinkData =\n    " + "\n    ".join(links) + " .")
    # The analytical transport keeps each connection's original destination.
    # This local authoritative resolver supplies the lookup handshake only.
    actors = [
        ActorDefinition("networkTransportActor",
            "makeTransportActor(transportAddr, nullAddr, nullAddr, dnsAddr, 'channel . 'cp4 . root)",
            "Shared network transport."),
        ActorDefinition("networkObserverActor", "mkAdversaryCp3(observerAddr, false)",
            "Network traffic observer."),
        ActorDefinition("authoritativeDnsServerActor",
            "< dnsAddr : Nameserver | db: (< 'cp4 . root, soa, 360000.0, soaData(360000.0) > "
            "< 'channel . 'cp4 . root, a, 360000.0, dnsAddr >), queue: nilQueue, "
            "forwardonly: nullAddr, queriesFwd: nilTAQL >",
            "Local authoritative DNS server for transport setup."),
    ]
    return policy, equations, actors


def generate_experiment(
    yaml_file: str | Path, output_dir: str | Path, *, scenario_name: str | None = None,
    user_models_dir: str | Path | None = None, seed: int | None = None,
    run_time: float | None = None, workload_start: float | None = None,
    workload_dir: str | Path | None = None,
) -> GeneratedExperiment:
    config = load_cp4_config(yaml_file, user_models_dir=user_models_dir, seed=seed)
    out = Path(output_dir).resolve()
    name = scenario_name or Path(yaml_file).stem
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
        raise Cp4ConfigError("scenario name must start with a letter and contain only letters, digits, _ or -")
    duration = config.conversation_duration if run_time is None else float(run_time)
    if duration <= 0:
        raise Cp4ConfigError("run time must be positive")
    number(duration)
    # A reproducible common input start replaces deployment/container wall time.
    start = (10.0 + random.Random(config.input_seed).uniform(0, config.max_start_delay)
             if workload_start is None else float(workload_start))
    number(start)
    library = ModelLibrary(config)
    addresses = {"ircMonitorAddr"}
    server_addrs = {server: f"ircServer{i}Addr" for i, server in enumerate(config.servers, 1)}
    addresses.update(server_addrs.values())
    sessions: dict[str, list[str]] = {addr: [] for addr in server_addrs.values()}
    peers: dict[str, list[str]] = {addr: [] for addr in server_addrs.values()}
    link_records: dict[str, list[str]] = {addr: [] for addr in server_addrs.values()}
    channels: list[ChannelEmission] = []
    actors: list[ActorDefinition] = []
    events: list[str] = []
    connections: list[dict[str, Any]] = []
    client_manifest: list[dict[str, Any]] = []

    def connection(prefix, kind, left, right, left_net, right_net, cfg, srv_cfg, client=None):
        left_ep, right_ep = prefix + "LeftEp", prefix + "RightEp"
        addresses.update((left_ep, right_ep))
        if kind == "direct":
            if cfg or srv_cfg:
                raise Cp4ConfigError("direct channels do not accept HCS parameters")
            emission = None
        else:
            cmodel, smodel = library.channel_models(kind, cfg, srv_cfg)
            emission = emit_channel(prefix, kind, left_ep, right_ep, left_net, right_net,
                                    cfg, srv_cfg, cmodel, smodel, stream_id=len(connections) + 1)
            channels.append(emission)
            addresses.update(emission.addresses)
        for local, peer, owner, side, network, peer_net, hcs in (
            (left_ep, right_ep, left, True, left_net, right_net, emission.client_endpoint if emission else ""),
            (right_ep, left_ep, right, False, right_net, left_net, emission.server_endpoint if emission else ""),
        ):
            if client:
                ctor = "mkIrcHcsSessionEndpoint" if emission else "mkIrcSessionEndpoint"
                record = f"{ctor}({local}, {owner}, {peer}, {str(side).lower()}, {client}" + (f", {hcs})" if emission else ")")
                if not emission:
                    record = f"withCp4Delay({record}, {number(config.one_way_delay(network, peer_net))})"
                sessions.setdefault(owner, []).append(record)
            else:
                ctor = "mkIrcHcsLinkEndpoint" if emission else "mkIrcLinkEndpoint"
                record = f"{ctor}({local}, {owner}, {peer}" + (f", {hcs})" if emission else ")")
                peers[owner].append(local)
                link_records[owner].append(record)
        connections.append(dict(name=prefix, kind="client" if client else "server", channel=kind,
            left=left, right=right, left_endpoint=left_ep, right_endpoint=right_ep,
            left_network=left_net, right_network=right_net, config=cfg, server_config=srv_cfg,
            hcs=emission.metadata if emission else {},
            user_models=emission.user_model_bindings if emission else {}))
        return left_ep

    for index, link in enumerate(config.links, 1):
        connection(f"peer{index}", link.channel.type,
            server_addrs[link.server_a], server_addrs[link.server_b],
            config.servers[link.server_a].network, config.servers[link.server_b].network,
            link.channel.config, {})
    for client in config.clients:
        addr, um = f"ircClient{client.index}Addr", f"ircUser{client.index}Addr"
        addresses.update((addr, um))
        endpoints = []
        for ordinal, conn in enumerate(client.connections):
            server = config.servers[conn.server]
            listener = server.client_channels.get(conn.channel.type)
            endpoints.append(connection(f"client{client.index}{'Primary' if ordinal == 0 else 'Backup'}",
                conn.channel.type, addr, server_addrs[conn.server], client.network, server.network,
                conn.channel.config, listener.config if listener else {}, addr))
        user_model = None
        if workload_dir:
            csv_path = Path(workload_dir) / f"{client.name}.csv"
            rooms, inputs = _csv_workload(csv_path)
            for time, room, payload in inputs:
                if time <= duration:
                    events.append(f"[{number(start + time)}, (to cp4Input({addr}) : Cp4ChatInput({quoted(room)}, {quoted(payload)})), 0]")
        else:
            rooms = list(config.profile_rooms(client.profile))
            _, _, op = library.add("irc", client.profile)
            key = op.removesuffix("-ma-v2")
            user_model = dict(actor=f"ircClient{client.index}WorkloadActor", address=um,
                              model=op, target=f"cp4Input({addr})")
            actors.append(ActorDefinition(user_model["actor"],
                f"mkIrcUMV2Actor({um}, {quoted(key)}, cp4Input({addr}))",
                f"IRC workload for {quoted(client.name)}, profile {quoted(client.profile)} "
                f"from {quoted(library.catalog[op]['source'])}."))
            events.append(f"[{number(start)}, (to {um} from {um} : burstDelayTO), 0]")
        room_list = " :: ".join(f"makeIrcChannelName({quoted(room)})" for room in rooms)
        actor = f"mkIrcClient-cp4({addr}, ({' ; '.join(endpoints)}), {quoted(client.name)}, ({room_list}))"
        destinations = ", ".join(
            f"{'primary' if ordinal == 0 else 'backup'} {quoted(conn.server)} via {conn.channel.type}"
            for ordinal, conn in enumerate(client.connections))
        actors.append(ActorDefinition(f"ircClient{client.index}Actor",
            f"withIrcSessions({actor}, {' '.join(sessions[addr])})",
            f"IRC client {quoted(client.name)} on {quoted(client.network)}; {destinations}."))
        events.append(f"[1.0, (to {addr} from {addr} : ClientStartConnect), 0]")
        client_manifest.append(dict(index=client.index, name=client.name, address=addr, network=client.network,
            node_type=client.node_type, profile=client.profile, user_model=user_model,
            channels=rooms, endpoints=endpoints,
            servers=[c.server for c in client.connections]))
    for name_, addr in server_addrs.items():
        # DNS joins Address/AddrList with other comma-separated kinds, making
        # the overloaded one/two-argument mkIrcServer ambiguous in mixed models.
        actor = (f"setAttrs(mkIrcServer({addr}), "
                 f"(peerServers: ({' ; '.join(peers[addr]) if peers[addr] else 'nil'}), "
                 "remoteChannelMap: emptyNameClientsMap))")
        if link_records[addr]:
            actor = f"withIrcLinks({actor}, {' '.join(link_records[addr])})"
        if sessions[addr]:
            actor = f"withIrcSessions({actor}, {' '.join(sessions[addr])})"
        actors.append(ActorDefinition(addr.removesuffix("Addr") + "Actor", actor,
            f"IRC server {quoted(name_)} on {quoted(config.servers[name_].network)}."))

    policy, net_equations, net_actors = _network(config, channels, addresses)
    actors += net_actors
    services = set().union(*(c.shared_services for c in channels)) if channels else set()
    if "s3" in services:
        actors.append(ActorDefinition("sharedS3ServerActor",
            "< s3SrvAddr : AwsS3HttpServer | thisAddr: s3SrvAddr, s3DataMap: emptyS3DataMap >",
            "Shared S3 cover service for Skyhook channels."))
    if "mastodon" in services:
        actors.append(ActorDefinition("sharedMastodonServerActor", "makeMastodonServer(masSrvAddr)",
            "Shared Mastodon cover service."))
    sources = [LIB / "irc/irc-cp4-workload.maude", LIB / "irc/irc-session-interface.maude",
               LIB / "irc/irc-link-interface.maude", LIB / "network/net_prob.maude",
               LIB.parent / "deps/dns_formalization/Maude/dns/probabilistic-model/dns.maude"]
    modules = ["IRC-CP4-WORKLOAD", "IRC-SESSION-INTERFACE", "IRC-LINK-INTERFACE", "CP4-NETWORK-POLICY", "NETWORK_CONNECTION", "DNS"]
    for channel in channels:
        sources.extend(channel.source_paths)
        modules.extend(channel.module_names)
        events.extend(channel.initial_events)
    modules += [model[1] for model in library.models.values()]
    lines = ["--- Generated CP4 experiment. Source parameters and mappings are in the manifest.",
             "set show advisories off .", "set print attribute off ."]
    lines += [f"sload {quoted(str(path))}" for path in dict.fromkeys(sources)]
    for model in library.catalog.values():
        lines += [f"--- {model['kind']} user model from {quoted(model['source'])}.",
                  f"sload {quoted(model['generated_file'])}"]
    lines += ["mod CP4-ADDRESSES is", "  inc ADDRESS .",
              "  ops " + " ".join(sorted(addresses)) + " : -> Address .", "endm", *policy,
              "mod CP4-EXPERIMENT is"]
    lines += [f"  inc {module} ." for module in dict.fromkeys(modules)]
    lines += ["  eq noiseMin(msg:Msg) = 0.0 .", "  eq noiseMax(msg:Msg) = 0.00001 .",
              "  --- Current CP4 ngIRCd PingTimeout/PongTimeout (seconds).",
              "  eq DefaultServerIdle = 120.0 .", "  eq DefaultServerPongWait = 120.0 .",
              "  op withCp4Delay : IrcSessionTable Float -> IrcSessionTable .",
              "  eq withCp4Delay(sessionEndpoint(E:Address, (AS:AttributeSet, wireDelay: D:Float)), N:Float)",
              "    = sessionEndpoint(E:Address, (AS:AttributeSet, wireDelay: N:Float)) ."]
    if any(channel.channel_type == "iodine" for channel in channels):
        lines += ["  eq fileSize = 0 .", "  eq packetSize = 530 .", "  eq maxPacketSize = 530 .",
                  "  eq pingInterval = 1.0 .", "  eq initialPingDelay = 0.001 .", "  eq receiveToPingDelay = 0.001 ."]
    if library.irc_map:
        lines.append("  eq MAModelMap = (" + ", ".join(f"({quoted(key)} |-> {op})" for key, op in library.irc_map.items()) + ") .")
    else:
        lines.append("  eq MAModelMap = empty .")
    lines += ["  " + eq for eq in net_equations]
    for conn in connections:
        if conn["kind"] == "server" and conn["channel"] == "direct":
            for src, dst, a, b in (
                (conn["left_endpoint"], conn["right_endpoint"], conn["left_network"], conn["right_network"]),
                (conn["right_endpoint"], conn["left_endpoint"], conn["right_network"], conn["left_network"]),
            ):
                lines += [f'  eq delayType(to {dst} from {src} : CP4BYTES:ByteSeq) = "Constant" .',
                          f'  eq delayConst(to {dst} from {src} : CP4BYTES:ByteSeq) = {number(config.one_way_delay(a, b))} .']
    connection_by_name = {conn["name"]: conn for conn in connections}
    entity_names = {addr: name_ for name_, addr in server_addrs.items()}
    entity_names.update({f"ircClient{client.index}Addr": client.name for client in config.clients})
    for channel in channels:
        conn = connection_by_name[channel.name]
        lines.append(f"  --- {channel.name}: {channel.channel_type} HCS, "
                     f"{quoted(entity_names[conn['left']])} <-> {quoted(entity_names[conn['right']])}.")
        for side, binding in channel.user_model_bindings.items():
            source = library.catalog[binding["model"]]["source"]
            lines.append(f"  --- {side.capitalize()} user model {quoted(source)} -> {binding['actor']}.")
        lines += ["  " + line for line in channel.declarations + channel.equations]
    for actor in actors:
        lines += [f"  --- {actor.description}", f"  op {actor.name} : -> Actor .",
                  f"  eq {actor.name} = {actor.expression} ."]
    lines += ["  op initState : Nat -> Config .", "  eq initState(seed:Nat) =", "    rCtr(seed:Nat)",
              "    mkIrcMonitor(ircMonitorAddr)"]
    lines += [f"    {actor.name}" for actor in actors]
    for channel in channels:
        lines += [f"    {actor}" for actor in channel.actors]
    lines += ["    " + event for event in events]
    lines += ["  .", "  op limit : -> Float .", f"  eq limit = {number(start + duration)} .",
              "  op initConfig : -> Config .", f"  eq initConfig = run({{0.0 | nil}} initState({config.input_seed}), limit) .",
              "endm", "set print attribute off .", "eof", ""]
    manifest = dict(schema_version=1, source=str(config.source_path), scenario=name, env=config.env,
        input_seed=config.input_seed, conversation_duration=duration, workload_start=start,
        max_start_delay=config.max_start_delay,
        end_time=start + duration, one_way_availability=config.one_way_availability,
        analysis_window_size=config.analysis_window_size,
        networks={key: asdict(value) for key, value in config.networks.items()},
        servers={key: dict(address=addr, network=config.servers[key].network) for key, addr in server_addrs.items()},
        clients=client_manifest, connections=connections, user_models=library.catalog,
        workload="csv" if workload_dir else "markov-v2",
        assumptions=["Maude stochastic profiles use the configured seed; they are not byte-identical to Python testbed timelines.",
            "Client registration starts at simulation second 1; workload uses a common reproducible start instead of container/minute synchronization.",
            "Transport uses the existing analytical TCP model and iodine DNS fragmentation; no container processes are executed.",
            "Iodine includes the configured DNS network as a collapsed forwarding hop; recursive cache/root/TLD behavior is not instantiated. TCP setup uses a local authoritative lookup.",
            "Public S3/Mastodon services add no netem latency unless minio_net/mastodon_net is configured.",
            "Each HCS connection has independent channel buffers and polling actors; public cover services and configured hashtags are shared.",
            "one_way_availability and analysis_window_size are retained as analysis metadata.",
            "The architecture YAML does not include the testbed's separate fault actions."])
    files = {**library.files, f"{name}.maude": "\n".join(lines),
             f"{name}_run.maude": f"sload {quoted(name + '.maude')}\nrew initConfig .\nquit\n",
             f"{name}_manifest.json": json.dumps(manifest, indent=2) + "\n"}
    # Build/validate everything before writing any experiment files.
    for relative, text in files.items():
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return GeneratedExperiment(out / f"{name}.maude", out / f"{name}_run.maude", out / f"{name}_manifest.json")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("yaml_file", help="CP4 reference-architecture YAML")
    parser.add_argument("--outDir", "--out-dir", dest="outDir", help="Output directory (default: beside YAML)")
    parser.add_argument("--scenarioName", "--scenario-name", dest="scenarioName")
    parser.add_argument("--user-models-dir", help="Override user_models beside the YAML")
    parser.add_argument("--seed", type=int, help="Override input_seed")
    parser.add_argument("--runTime", "--run-time", dest="runTime", type=float, help="Conversation duration in seconds")
    parser.add_argument("--workload-start", type=float, help="Absolute simulation time for workload input")
    parser.add_argument("--workload-dir", help="Testbed-format CSVs named alice1.csv, alice2.csv, etc.")


def generate(args: argparse.Namespace) -> GeneratedExperiment:
    return generate_experiment(args.yaml_file, args.outDir or Path(args.yaml_file).resolve().parent,
        scenario_name=args.scenarioName, user_models_dir=args.user_models_dir, seed=args.seed,
        run_time=args.runTime, workload_start=args.workload_start, workload_dir=args.workload_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args()
    try:
        result = generate(args)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Generated {result.scenario}\nRun: maude {result.runner}\nManifest: {result.manifest}")


if __name__ == "__main__":
    main()
