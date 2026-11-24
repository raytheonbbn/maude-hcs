"""Compose independent, bidirectional CP4 hidden channels.

The application addresses are opaque ByteSeq endpoints.  They may belong to an
IRC client session or to an IRC server link; the channel actors do not need to
know which.  Network transport, shared public services and user-model imports
are assembled by the experiment generator.
"""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


LIB = Path(__file__).resolve().parent / "lib"
ALIASES = {"obfs": "obfs4", "racetunnel": "webtunnel"}
_PROTOCOL_LABELS = {
    "obfs4": "Obfs4",
    "webtunnel": "WebTunnel",
    "iodine": "Iodine",
    "skyhook": "Skyhook",
    "mastodon": "Mastodon",
}
_ACTOR_ROLES = {
    "Proxy": "ServerProxy",
    "SendApp": "SendApplication",
    "RcvApp": "ReceiveApplication",
    "ClientCm": "ClientContentManager",
    "ServerCm": "ServerContentManager",
    "ClientSdk": "ClientS3Adapter",
    "ServerSdk": "ServerS3Adapter",
    "ClientUm": "ClientUserModel",
    "ServerUm": "ServerUserModel",
    "ClientHttp": "ClientHttpAdapter",
    "ServerHttp": "ServerHttpAdapter",
}


@dataclass
class ChannelEmission:
    """Maude fragments plus the network attachment points of one HCS."""

    name: str
    channel_type: str
    client_endpoint: str = ""
    server_endpoint: str = ""
    addresses: list[str] = field(default_factory=list)
    declarations: list[str] = field(default_factory=list)
    equations: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    initial_events: list[str] = field(default_factory=list)
    source_paths: list[Path] = field(default_factory=list)
    module_names: list[str] = field(default_factory=list)
    # Only the on-wire actors belong here; adapters/UMs are local operations.
    network_endpoints: dict[str, str] = field(default_factory=dict)
    # DNS does not use TCP.  These links require direct network scheduling.
    network_links: list[tuple[str, str, str, str]] = field(default_factory=list)
    shared_services: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    user_model_bindings: dict[str, dict[str, str]] = field(default_factory=dict)

    def add_actor(self, suffix: str, expression: str) -> str:
        protocol = _PROTOCOL_LABELS[self.channel_type]
        role = _ACTOR_ROLES.get(suffix, suffix)
        actor = self.name + protocol + role + "Actor"
        self.declarations.append(f"op {actor} : -> Actor .")
        self.equations.append(f"eq {actor} = {expression} .")
        self.actors.append(actor)
        return actor

    def address(self, suffix: str) -> str:
        address = self.name + suffix + "Addr"
        self.addresses.append(address)
        return address

    def load(self, path: str, *modules: str) -> None:
        self.source_paths.append(LIB / path)
        self.module_names.extend(modules)

    def start(self, address: str, content: str, *, sender: bool = True) -> None:
        source = f" from {address}" if sender else ""
        self.initial_events.append(f"[0.0, (to {address}{source} : {content}), 0]")


def _string(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def skyhook_uuid(value: str) -> str:
    """Encode opaque testbed UUID seeds as abstract decimal generations.

    SKYHOOK_AUX advances object IDs by integer successor.  A large namespace
    for each seed preserves distinct bidirectional streams in a shared bucket
    without pretending to implement cryptographic SHA-256 in Maude.
    """
    digest = hashlib.sha256(str(value).encode("utf-8")).digest()
    return str(int.from_bytes(digest[:16], "big") << 64)


def emit_channel(
    name: str,
    channel_type: str,
    client_app: str,
    server_app: str,
    client_network: str,
    server_network: str,
    config: Mapping[str, Any] | None = None,
    server_config: Mapping[str, Any] | None = None,
    client_model: str = "",
    server_model: str = "",
    *,
    stream_id: int = 0,
    s3_service: str = "s3SrvAddr",
    mastodon_service: str = "masSrvAddr",
) -> ChannelEmission:
    """Emit real HCS actors, without creating any IRC actors.

    ``client_model`` and ``server_model`` are Maude model constants generated
    from this channel's JSON action models.  They are required for Skyhook and
    Mastodon.  ``config`` contains the initiating endpoint configuration;
    ``server_config`` contains listener defaults from ``client_channels``.
    Each invocation creates its own buffers, polling actors, DNS fragments,
    TLS connection and endpoint addresses.
    """
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid Maude channel prefix: {name!r}")
    kind = ALIASES.get(channel_type, channel_type)
    if kind not in {"obfs4", "webtunnel", "iodine", "skyhook", "mastodon"}:
        raise ValueError(f"Unsupported HCS channel type: {channel_type!r}")
    cfg = dict(config or {})
    srv = dict(server_config or {})
    out = ChannelEmission(name, kind)
    if kind in {"skyhook", "mastodon"} and not (client_model and server_model):
        raise ValueError(f"{kind} requires both client and server user models")

    if kind == "obfs4":
        if cfg.get("iat_mode", 0) != 0 or srv.get("iat_mode", 0) != 0:
            raise ValueError("The current Obfs4 model supports only iat_mode: 0")
        out.load("obfs4/obfs4_prob.maude", "OBFS4")
        left, right = out.address("Client"), out.address("Server")
        out.add_actor("Client", f"makeObfs4Node({left}, {client_app}, {right})")
        out.add_actor("Server", f"makeObfs4Node({right}, {server_app}, {left})")
        out.network_endpoints.update({left: client_network, right: server_network})

    elif kind == "webtunnel":
        out.load("webtunnel/webtunnel_prob.maude", "WEBTUNNEL")
        left, right = out.address("Client"), out.address("Proxy")
        tls = cfg.get("tls_name", srv.get("tls_name", "irc.pwnd.com"))
        path = cfg.get("upgrade_path", srv.get("upgrade_path", "secret/path/v1"))
        out.add_actor("Client", f"< {left} : WtClient | thisAddr: {left}, "
                      f"serverProxyAddr: {right}, ircServerAddr: {server_app}, "
                      f"ircClientAddr: {client_app}, tlsServerName: {_string(tls)}, "
                      f"upgradePath: {_string(path)}, tunnelState: Closed, pendingMsgs: emptyQueue >")
        out.add_actor("Proxy", f"makeWtServerProxy({right}, {server_app})")
        out.start(left, "WtStartCmd")
        out.network_endpoints.update({left: client_network, right: server_network})
        out.metadata.update(tls_name=tls, port=cfg.get("port", srv.get("port")))

    elif kind == "iodine":
        # IODINE-PARAMETERS installs the stream sampler equation, whose
        # samplerRandom hook is declared by SAMPLER-X.
        out.load("common/maude/sampler-x.maude", "SAMPLER-X")
        out.load("dns/maude/probabilistic/iodine_dns.maude", "IODINE_DNS")
        left, right = out.address("SendApp"), out.address("RcvApp")
        client, server = out.address("DnsClient"), out.address("DnsServer")
        query = _positive_int(cfg.get("max_query_length", srv.get("max_query_length", 200)), "max_query_length")
        response = _positive_int(srv.get("max_response_size", cfg.get("max_response_size", 460)), "max_response_size")
        out.add_actor("SendApp", f"mkSendAppWithStream({left}, {right}, {client_app}, {client}, {2 * stream_id})")
        out.add_actor("RcvApp", f"mkRcvAppWithStream({right}, {left}, {server_app}, {server}, {2 * stream_id + 1})")
        domain = f"'{name.lower()} . 'pwnd . 'com . root"
        out.add_actor("DnsClient", f"withIodineFragmentLimits(makeWClient({client}, {server}, {domain}, a, 0.0), {query}, {response})")
        out.add_actor("DnsServer", f"withIodineFragmentLimits(makeWNameServer({server}, 0.0, "
                      f"< 'pwnd . 'com . root, soa, 360000.0, soaData(360000.0) >), {query}, {response})")
        out.start(left, "start", sender=False)
        out.start(right, "start", sender=False)
        out.network_links.append((client, server, client_network, server_network))
        out.metadata.update(max_query_length=query, max_response_size=response,
                            size_semantics="abstract DNS fragment bounds")

    elif kind == "skyhook":
        out.load("raceboatSkyhook/maude/rb-cm-simple-bi.maude", "CONTENT-MANAGER-SIMPLE-BI")
        out.load("skyhook/skyhook_prob.maude", "SKYHOOK")
        out.load("s3/s3_protocol.maude", "S3_PROTOCOL")
        out.load("common/maude/user-action-actor.maude", "USER-ACTION-ACTOR")
        left, right = out.address("ClientCm"), out.address("ServerCm")
        pu, ah = out.address("PublicUser"), out.address("AccountHolder")
        client_sdk, server_sdk = out.address("ClientSdk"), out.address("ServerSdk")
        client_um, server_um = out.address("ClientUm"), out.address("ServerUm")
        fetch_bucket = str(cfg.get("fetch_bucket", name + "-server-to-client"))
        post_bucket = str(cfg.get("post_bucket", name + "-client-to-server"))
        fetch_seed = str(cfg.get("initial_fetch_uuid", "server-seed"))
        post_seed = str(cfg.get("post_uuid", "client-seed"))
        fetch_id, post_id = skyhook_uuid(fetch_seed), skyhook_uuid(post_seed)
        if fetch_bucket == post_bucket and fetch_id == post_id:
            raise ValueError("Skyhook directions in the same bucket need distinct initial UUIDs")
        out.equations.append(f"--- Skyhook UUID seeds {_string(fetch_seed)} / {_string(post_seed)} "
                             "are encoded as separate decimal generation namespaces.")
        out.add_actor("ClientCm", f"mkCMSimpleBi({left}, {client_app}, {pu})")
        out.add_actor("ServerCm", f"mkCMSimpleBi({right}, {server_app}, {ah})")
        out.add_actor("PublicUser", f"makeSkyhookPU({pu}, {left}, {client_sdk}, "
                      f"{_string(fetch_bucket)}, {_string(post_bucket)}, {_string(fetch_id)}, {_string(str(int(post_id) + 1))})")
        out.add_actor("AccountHolder", f"mkSkyhookAH({ah}, {right}, {server_sdk}, "
                      f"{_string(post_bucket)}, {_string(fetch_bucket)}, {_string(post_id)}, "
                      f"{_string(fetch_id)}, {_string(fetch_id)}, "
                      f"{_positive_int(cfg.get('open_objects', 100), 'open_objects')})")
        out.add_actor("ClientSdk", f"makeS3Client({client_sdk}, {s3_service})")
        out.add_actor("ServerSdk", f"makeS3Client({server_sdk}, {s3_service})")
        client_um_actor = out.add_actor("ClientUm", f"mkUMactor({client_um}, {client_model}, {left})")
        server_um_actor = out.add_actor("ServerUm", f"mkUMactor({server_um}, {server_model}, {right})")
        out.user_model_bindings.update(
            client=dict(actor=client_um_actor, address=client_um, model=client_model, target=left),
            server=dict(actor=server_um_actor, address=server_um, model=server_model, target=right),
        )
        out.start(ah, "SkyhookStartCmd")
        out.start(client_um, 'actionR("ok")')
        out.start(server_um, 'actionR("ok")')
        out.network_endpoints.update({client_sdk: client_network, server_sdk: server_network})
        out.shared_services.add("s3")
        out.metadata.update(fetch_bucket=fetch_bucket, post_bucket=post_bucket,
                            fetch_uuid=fetch_id, post_uuid=str(int(post_id) + 1))

    else:  # Mastodon
        out.load("raceboatMastodon/maude/enc-dec-actor.maude", "ENC-DEC")
        out.load("raceboatMastodonBidir/maude/rb-cm-bidir-mas.maude", "CONTENT-MANAGER-BIDIR")
        out.load("mastodon/maude/probabilistic/mastodon.maude", "MASTODON")
        out.load("common/maude/user-action-actor.maude", "USER-ACTION-ACTOR")
        left, right = out.address("ClientCm"), out.address("ServerCm")
        client_http, server_http = out.address("ClientHttp"), out.address("ServerHttp")
        client_ed, server_ed = out.address("ClientCodec"), out.address("ServerCodec")
        client_um, server_um = out.address("ClientUm"), out.address("ServerUm")
        # The listener reverses its send/receive tags for the initiating end.
        send = str(cfg.get("hashtag_send", srv.get("hashtag_recv", name + "-up")))
        recv = str(cfg.get("hashtag_recv", srv.get("hashtag_send", name + "-down")))
        out.add_actor("ClientCm", f"mkCMSndRcvActor({left}, {client_ed}, {client_http}, {client_app}, {_string(send)}, {_string(recv)})")
        out.add_actor("ServerCm", f"mkCMSndRcvActor({right}, {server_ed}, {server_http}, {server_app}, {_string(recv)}, {_string(send)})")
        out.add_actor("ClientHttp", f"makeMastodonClient({client_http}, {mastodon_service}, {left})")
        out.add_actor("ServerHttp", f"makeMastodonClient({server_http}, {mastodon_service}, {right})")
        images = " :: ".join(f"image({i}, 190000, 3000)" for i in range(1, 11))
        out.add_actor("ClientCodec", f"makeDestiniActor({client_ed}, {images})")
        out.add_actor("ServerCodec", f"makeDestiniActor({server_ed}, {images})")
        client_um_actor = out.add_actor("ClientUm", f"mkUMactor({client_um}, {client_model}, {left})")
        server_um_actor = out.add_actor("ServerUm", f"mkUMactor({server_um}, {server_model}, {right})")
        out.user_model_bindings.update(
            client=dict(actor=client_um_actor, address=client_um, model=client_model, target=left),
            server=dict(actor=server_um_actor, address=server_um, model=server_model, target=right),
        )
        out.start(client_um, 'actionR("ok")')
        out.start(server_um, 'actionR("ok")')
        out.network_endpoints.update({client_http: client_network, server_http: server_network})
        out.shared_services.add("mastodon")
        out.metadata.update(hashtag_send=send, hashtag_recv=recv)

    out.client_endpoint, out.server_endpoint = left, right
    out.declarations.insert(0, "ops " + " ".join(out.addresses) + " : -> Address .")
    return out
