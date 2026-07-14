# © 2026 The Johns Hopkins University Applied Physics Laboratory LLC

import math
from collections import defaultdict
from maude_hcs import PROJECT_TOPLEVEL_DIR

from .container_helper import (
    DEFAULT_CLIENT_CONTAINERS,
    DEFAULT_DNS_CONTAINERS,
    DEFAULT_IRC_SERVER_CONTAINERS,
    DEFAULT_MASTODON_CONTAINERS,
    DEFAULT_MINIO_CONTAINERS,
    DEFAULT_ROUTER_CONTAINERS,
    DEFAULT_SERVER_CONTAINERS,
    DEFAULT_SERVER_RACETUNNEL_CONTAINERS,
    DEFAULT_TGEN_CONTAINERS,
    DEFAULT_TGEN_PER_CONTAINER,
)

from .file_handling import read_yaml
from .net_start_helpers import get_ips, get_subnets

NETWORK_TOPOLOGY_PATH = PROJECT_TOPLEVEL_DIR / "parsers" / "tne_parser" / "network_topology.json"

def get_client_node_info(vals):
    clients_per_net = vals["client_per_network"]
    return clients_per_net


def get_tgen_node_info(vals):
    clients_per_net = vals["tgen_per_network"]
    return clients_per_net


def get_network_type(network_dict, net_key):
    return network_dict[net_key]["network"]


def generate_containers(node_type, quantity, default_containers, start_val):
    # print(node_type, quantity, default_containers)
    return [
        f"{container}_{node_type}_{i}"
        for i in range(start_val, start_val + quantity)
        for container in default_containers
    ]


def get_server_network_name(test_config, look):
    # Not for searching for client network name,
    # only for single instances of a network type (server, mastodon, minio)
    if look == "router":
        return "router_net"
    for net_name, vals in test_config["network"].items():
        if vals["network"] == look:
            return net_name


def server_containers_per_net(test_config, look, default_cont):
    network_info = {}
    net_name = get_server_network_name(test_config, look)
    network_info = {
        net_name: {"containers": []}
    }  # Each server network has its own router
    if net_name != "router_net":
        net_router = f"router_{net_name}"
        network_info[net_name]["containers"].append(net_router)
    network_info[net_name]["containers"].extend(default_cont)
    return network_info


def calculate_tgen_cont_qnt(tgen_config):
    num_tgen = tgen_config["quantity"]
    return math.ceil(num_tgen / DEFAULT_TGEN_PER_CONTAINER)


def client_server_containers_per_net(test_config):
    # Get network information for services
    client_network_info = {}
    server_net = get_server_network_name(test_config, "server")
    server_per_network = {
        server_net: {"containers": [f"router_{server_net}"]}
    }  # Will have its own router

    if "nodes" in test_config and test_config["nodes"]:
        for node_type, vals in test_config["nodes"].items():
            # Assuming these are all client
            clients_per_net = get_client_node_info(vals)
            for network, config in clients_per_net.items():
                client_network_info.setdefault(network, {})
                client_network_info[network].setdefault(node_type, 0)
                client_network_info[network][node_type] += config["quantity"]

    if "tgen" in test_config and test_config["tgen"]:
        for tgen_type, vals in test_config["tgen"].items():
            # Assuming these are all tgen
            tgens_per_net = get_tgen_node_info(vals)
            # print("TGEN")
            # print(tgens_per_net)
            for network, config in tgens_per_net.items():
                # print(f"{network} -> {config}")
                client_network_info.setdefault(network, {})
                client_network_info[network].setdefault(tgen_type, 0)
                client_network_info[network][
                    tgen_type
                ] += calculate_tgen_cont_qnt(config)

    # print(f"Client network info={client_network_info=}")
    clients_per_network = {}
    server_containers = []
    client_containers = []
    irc_node_count = 1
    tgen_node_count = {}
    for network, requested in client_network_info.items():
        clients_per_network.setdefault(
            network, {"containers": [f"router_{network}", f"dns_{network}"]}
        )  # Router and DNS are already guaranteed to be on each client network
        for node_type, quantity in requested.items():
            if "tgen_" in node_type:

                if node_type not in tgen_node_count.keys():
                    tgen_node_count[node_type] = 1

                if network == "server_net":
                    server_containers = generate_containers(
                        node_type,
                        quantity,
                        DEFAULT_TGEN_CONTAINERS,
                        tgen_node_count[node_type],
                    )
                else:
                    client_containers = generate_containers(
                        node_type,
                        quantity,
                        DEFAULT_TGEN_CONTAINERS,
                        tgen_node_count[node_type],
                    )

                tgen_node_count[node_type] += quantity
            else:
                if "racetunnel" in node_type:
                    server_containers = generate_containers(
                        node_type,
                        quantity,
                        DEFAULT_SERVER_RACETUNNEL_CONTAINERS,
                        irc_node_count,
                    )
                elif "iodine" not in node_type:
                    server_containers = generate_containers(
                        node_type,
                        quantity,
                        DEFAULT_SERVER_CONTAINERS,
                        irc_node_count,
                    )
                else:
                    server_containers = []

                client_containers = generate_containers(
                    node_type,
                    quantity,
                    DEFAULT_CLIENT_CONTAINERS,
                    irc_node_count,
                )
                irc_node_count += quantity
            # Since the DEFAULT_SERVER_CONTAINERS only consist of
            # the bob container, use it as a counter for total nodes
            clients_per_network[network]["containers"].extend(
                client_containers
            )
            server_per_network[server_net]["containers"].extend(
                server_containers
            )
            server_per_network[server_net]["containers"].extend(
                server_containers
            )
    server_per_network[server_net]["containers"].extend(
        DEFAULT_IRC_SERVER_CONTAINERS
    )
    return clients_per_network, server_per_network


def add_tgen_servers(server_net, server_network_info):
    server_network_info[server_net]["containers"].extend(
        ["ftp_server", "tls_server", "gorilla_server"]
    )
    return server_network_info


def add_subnets_to_section(network_dict, subnet_list):
    for net_name, subnet in zip(network_dict.keys(), subnet_list):
        network_dict[net_name]["network"] = subnet


def add_subnet_info(network_info, net_data, type_of_net):
    subnet = net_data[type_of_net]["priv_net"]
    net_num = len(network_info.keys())
    subnets = get_subnets(subnet, 24, net_num)
    add_subnets_to_section(network_info, subnets)


def the_whole_network_info(test_config, net_data, look, default_container):
    network_info = server_containers_per_net(
        test_config, look, default_container
    )
    add_subnet_info(network_info, net_data, look)
    return network_info


def gather_routers(network_info):
    for net, vals in network_info.items():
        if "router" in net:
            continue
        else:
            router_container = [
                container
                for container in vals["containers"]
                if "router" in container
            ]
            network_info["router_net"]["containers"].extend(router_container)


def add_ips_to_containers(network_info):
    for net, vals in network_info.items():
        network_info[net]["container_info"] = {}
        ips = get_ips(vals["network"])
        containers = vals["containers"]
        for container, ip in zip(containers, ips):
            network_info[net]["container_info"][container] = str(ip)
        vals.pop("containers")


def merge_to_lists(*dicts):
    merged = defaultdict(lambda: {"containers": []})
    for d in dicts:
        for k, v in d.items():
            # pprint(v)
            new_containers = v.get("containers", [])
            merged[k]["containers"].extend(new_containers)
            merged[k]["network"] = v.get("network")
    return dict(merged)


def go_network_gen(test_config):
    """
    Generates network information for each service in test config
    Maps services to networks in net data
    Gets static ips for containers
    Writes to network_map.json
    """

    net_data = read_yaml(NETWORK_TOPOLOGY_PATH)

    env_name = test_config.get("env", "pwnd_cp3_env")
    server_net = get_server_network_name(test_config, "server")

    (
        client_network_info,
        server_network_info,
    ) = client_server_containers_per_net(test_config)
    server_network_info = add_tgen_servers(server_net, server_network_info)

    add_subnet_info(server_network_info, net_data, "server")
    add_subnet_info(client_network_info, net_data, "client")

    minio_network_info = the_whole_network_info(
        test_config, net_data, "minio", DEFAULT_MINIO_CONTAINERS
    )
    mastodon_network_info = the_whole_network_info(
        test_config, net_data, "mastodon", DEFAULT_MASTODON_CONTAINERS
    )
    dns_network_info = the_whole_network_info(
        test_config, net_data, "dns", DEFAULT_DNS_CONTAINERS
    )
    router_network_info = the_whole_network_info(
        test_config, net_data, "router", DEFAULT_ROUTER_CONTAINERS
    )
    entire_network_info = merge_to_lists(
        # tgen_network_info,
        client_network_info,
        server_network_info,
        minio_network_info,
        mastodon_network_info,
        dns_network_info,
        router_network_info,
    )
    gather_routers(entire_network_info)
    # print(f"{entire_network_info=}")
    add_ips_to_containers(entire_network_info)

    return entire_network_info