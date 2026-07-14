# © 2025 The Johns Hopkins University Applied Physics Laboratory LLC

import ipaddress
import logging
from typing import Optional

from netaddr import IPNetwork

import docker

logger = logging.getLogger(__name__)


def get_dns_ip(container_info, default_dns):
    """
    Gettings either local dns ip or public dns ip
    """
    for container, ip in container_info.items():
        if ("dns" in container) and ("tgen_type_dns" not in container):
            return ip
    return default_dns


def get_ips(subnet):
    network = ipaddress.ip_network(subnet)
    hosts = list(network.hosts())[1:]
    return [str(ip) for ip in hosts]


def get_subnets(network, prefix, count):
    # returns 10.0.1.0/24, 10.0.2.0/24 ....
    net = IPNetwork(network)
    subnets = net.subnet(prefix)
    return [str(next(subnets)) for _ in range(count)]


def _find_network_via_sdk(entity: str) -> Optional[str]:
    """
    Use the Docker SDK to locate a network whose *name* contains ``entity``.
    Returns the exact network name if exactly one match is found,
    otherwise ``None`` (caller decides what to do).
    """
    client = docker.from_env()
    # Docker filters accept regular‑expression like patterns;
    # we just ask for all and post‑filter in Python to keep the
    # logic simple.
    networks = client.networks.list()
    matches = [net.name for net in networks if entity in net.name]
    if not matches:
        logger.debug("No Docker network contains %r", entity)
        return None
    if len(matches) > 1:
        logger.warning(
            "Multiple Docker networks match %r: %s – returning the first one",
            entity,
            ", ".join(matches),
        )
    return matches[0]


def get_local_network_name(entity: str) -> str:
    """
    Resolve the Docker network name that belongs to ``entity``.
    The resolution order is:
    """
    if not isinstance(entity, str) or not entity:
        raise ValueError("`entity` must be a non‑empty string")

    net = _find_network_via_sdk(entity)
    if net:
        return net

    raise RuntimeError(
        f"Could not locate a Docker network containing the token '{entity}'. "
        "Make sure the network exists and that the current user "
        "has permission to query Docker."
    )
