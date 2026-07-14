# © 2026 The Johns Hopkins University Applied Physics Laboratory LLC

DEFAULT_IMAGE_TAG = "cp3"
DEFAULT_TGEN_CONTAINERS = ["tgen"]
DEFAULT_CLIENT_CONTAINERS = ["alice", "irc"]
DEFAULT_SERVER_CONTAINERS = ["bob"]
DEFAULT_SERVER_RACETUNNEL_CONTAINERS = DEFAULT_SERVER_CONTAINERS + [
    "reverse_proxy_bob"
]
DEFAULT_IRC_SERVER_CONTAINERS = ["irc_server"]
DEFAULT_MINIO_CONTAINERS = ["reverse_proxy", "minio_server"]
DEFAULT_DNS_CONTAINERS = ["public_dns", "auth_dns", "tld_dns", "root_dns"]
DEFAULT_MASTODON_CONTAINERS = [
    "mastodon_proxy",
    "mastodon_redis",
    "mastodon_web",
    "mastodon_streaming",
    "mastodon_sidekiq",
    "mastodon_db",
]
DEFAULT_ROUTER_CONTAINERS = ["router_ixp"]
DEFAULT_TGEN_PER_CONTAINER = 1