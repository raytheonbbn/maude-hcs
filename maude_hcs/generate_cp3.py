#!/usr/bin/env python3

# Generate scenario HCSs and TGENs with one TransportActor and lossless links.
# Scenario delays and user profiles are preserved.
# Parses network topology, TGEN traffic profiles, loss profiles, and parameters dynamically from the scenario YAML configuration.
# Guarantees:
# - scenario1.maude contains ONLY readable address names (zero structured addresses 'a(...)').
# - scenario1_addresses.maude maps readable address names to structured addresses.
# - cl[N] refers to the NetId of the client network, not individual clients.

import os
import sys
from venv import logger
import yaml
import argparse
from pathlib import Path
import math
import json
import shutil
from maude_hcs.lib import GLOBALS

from .generate_quatex import Config, write_all_queries_to_file

IMAGE_SIZE = 190000
smc_mod_name = "HCS_TEST"
MAX_BL_SIZE = 10000.0 # max list size
  
# Define the features as a list of strings to make them easily reusable and modifiable
# Changed to dictionary to keep track of the required naming scheme for T&E results
FEATURES = {
    "dnsQueryRate": "dns_query_rate",
    "dnsQuerySize": "dns_query_size_mean",
    "dnsRespSize": "dns_response_size_mean",
    "tcpUpRate": "tcp_upload_rate",
    "tcpDownRate": "tcp_download_rate",
    "tcpUpToDownRate": "tcp_upload_download_ratio",
    "tcpOutPktRate": "tcp_outgoing_packet_rate",
    "tcpInPktRate": "tcp_incoming_packet_rate",
    "tcpOutToInPktRate": "tcp_packet_upload_download_ratio",
    "tcpPktSizeStdDev": "packet_size_std_dev",
    "tcpPktSize": "packet_size_mean",
    "tcpPktInterarrival": "packet_interarrival_mean",
    "tcpDirectionChange": "direction_change_count",
    "tcpActiveFlow": "active_flow_count",
    "tcpNewCnx": "tcp_new_conn_count",
}

VANTAGE_POINTS = (
    "client_net_iodine",
    "client_net_mastodon",
    "client_net_obfs",
    "client_net_racetunnel",
    "client_net_sky",
    "ixp-router",
    "mastodon_net",
    "minio_net",
    "server_net",
)

def filter_feats(substrs: list[str]) -> dict:
    """Return a new features dictionary (a subset of FEATURES)
    containing only features matching some given substr"""

    # Returns True if any substr is in either the key or value
    def filt(tup: tuple[str, str]):
        k, v = tup
        for substr in substrs:
            if substr in k or substr in v:
                return True
        return False


    new_items = filter(
        filt,
        FEATURES.items()
    )

    return dict(new_items)

def filter_vpts(substrs: list[str]) -> list[str]:
    """Return a new list of vantage points (a subset of VANTAGE_POINTS)
    containing only vpts matching some given substr"""

    def filt(vpt: str):
        for substr in substrs:
            if substr in vpt:
                return True
        return False

    return list(filter(filt, VANTAGE_POINTS))

def chunk_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def fmt(val):
    s = f"{float(val / 100.0):.5f}".rstrip("0")
    return s + "0" if s.endswith(".") else s

def load_loss_profile(profile_name, base_dir):
    """Load loss parameters from tc_user_models/{profile_name}.yaml if present, or raise an exception."""
    profile_path = os.path.join(base_dir, "tc_user_models", f"{profile_name}.yaml")
    if not os.path.exists(profile_path):
        parent_tc = os.path.join(base_dir, "..", "tc_user_models", f"{profile_name}.yaml")
        if os.path.exists(parent_tc):
            profile_path = parent_tc
    if os.path.exists(profile_path):
        with open(profile_path, "r") as f:
            data = yaml.safe_load(f)
            return {
                "p13": fmt(data["p13"]),
                "p31": fmt(data["p31"]),
                "p32": fmt(data["p32"]),
                "p23": fmt(data["p23"]),
                "p14": fmt(data["p14"])
            }
    if profile_name == "none":
        return {
                "p13": "0.0",
                "p31": "0.0",
                "p32": "0.0",
                "p23": "0.0",
                "p14": "0.0"
        }    
    raise FileNotFoundError(f"Could not find loss profile '{profile_name}' in {base_dir}")    

def parse_scenario_yaml(yaml_path):
    with open(yaml_path, "r") as f:
        config = yaml.safe_load(f)
        
    base_dir = os.path.dirname(os.path.abspath(yaml_path))
    duration = float(config.get("conversation_duration", 11700))
    analysis_window_size = float(config.get("analysis_window_size", 900))    

    # Parse networks
    networks = {}
    loss_profiles = {}
    net_data = config.get("network", {})
    for net_name, n_info in net_data.items():
        params = n_info.get("params", {}).get("upstream", {})
        params_down = n_info.get("params", {}).get("downstream", {})
        assert params_down == params, f'Expecting network params to be symmetric but they arent for {net_name}'
        latency = float(params.get("latency", 10))
        loss_prof_name = params.get("loss_profile", "good")
        networks[net_name] = (latency, loss_prof_name)
        if loss_prof_name not in loss_profiles:
            loss_profiles[loss_prof_name] = load_loss_profile(loss_prof_name, base_dir)

    # Assign NetIds: client networks get cl[1], cl[2], ...; servers get srvN, minN, masN, dnsN
    net_id_map = {}
    cl_idx = 1
    for net_name in networks:
        if net_name.startswith("client_net_"):
            net_id_map[net_name] = f"cl[{cl_idx}]"
            cl_idx += 1
        elif net_name == "server_net":
            net_id_map[net_name] = "srvN"
        elif net_name == "minio_net":
            net_id_map[net_name] = "minN"
        elif net_name == "mastodon_net":
            net_id_map[net_name] = "masN"
        elif net_name == "dns_net":
            net_id_map[net_name] = "dnsN"
        else:
            raise Exception(f'Do no know how to map {net_name}, not a known client or server net')
            

    # Short names for Maude operators
    net_short = {}
    for net_name in networks:
        if "mastodon" in net_name and "client" in net_name:
            net_short[net_name] = "Mas"
        elif "mastodon" in net_name:
            net_short[net_name] = "MasNet"
        elif "racetunnel" in net_name:
            net_short[net_name] = "Rt"
        elif "iodine" in net_name:
            net_short[net_name] = "Iod"
        elif "obfs" in net_name:
            net_short[net_name] = "Obfs"
        elif "sky" in net_name:
            net_short[net_name] = "Sky"
        elif "server" in net_name:
            net_short[net_name] = "Srv"
        else:
            net_short[net_name] = "".join(p.capitalize() for p in net_name.split("_"))

    # Channel mapping
    channel_map = {
        "racetunnel": "webtunnel",
        "skyhook": "skyhook",
        "obfs": "obfs4",
        "iodine": "iodine",
        "mastodon": "mastodon",
    }

    # Parse HCS nodes and Channel Models
    hcs_nodes = []
    hcs_profiles_by_channel = {}
    hcs_channel_models = {}
    
    nodes_data = config.get("nodes", {})
    for node_type, n_info in nodes_data.items():
        channel_cfg = n_info.get("channel_config", [{}])[0]
        channel_raw = channel_cfg.get("channel", "")
        channel = channel_map.get(channel_raw, channel_raw)
        
        # Extract custom user models if present
        vars_cfg = channel_cfg.get("vars", {})
        c_model = vars_cfg.get("client", {}).get("user_model", "")
        s_model = vars_cfg.get("server", {}).get("user_model", "")
        if c_model.endswith(".json"): c_model = c_model[:-5]
        if s_model.endswith(".json"): s_model = s_model[:-5]
        if c_model or s_model:
            hcs_channel_models[channel] = {"client": c_model, "server": s_model}
   
        cpn = n_info.get("client_per_network", {})
        for net_name, c_info in cpn.items():
            qty = int(c_info.get("quantity", -1))
            assert qty > 0, f'node {net_name} has qty 0'
            profs_dict = c_info.get("profiles", {})
            profs_list = [(p, float(w)) for p, w in profs_dict.items()]
            hcs_nodes.append((channel, net_name, qty, profs_list))
            hcs_profiles_by_channel[channel] = profs_list

    # Parse TGENs
    tgen_type_map = {
        "tgen_type_mastodon": "masTgen",
        "tgen_type_ftp": "ftpTgen",
        "tgen_type_dns": "dnsTgen",
        "tgen_type_minio": "minTgen",
        "tgen_type_gorilla": "gorTgen",
        "tgen_type_irc": "ircTgen",
    }
    tgen_defs = {}
    tgen_data = config.get("tgen", {})
    for tkey, t_val in tgen_data.items():
        if tkey.endswith("_monitor"):
            continue  # Ignore monitors per scenario spec
        internal_type = tgen_type_map.get(tkey, tkey)
        net_dict = {}
        for net_name, tpn_info in t_val.get("tgen_per_network", {}).items():
            qty = int(tpn_info.get("quantity", -1))
            assert qty > 0, f'tgen {net_name} has qty 0'
            profs_dict = tpn_info.get("profiles", {})
            profs_list = [(p, float(w)) for p, w in profs_dict.items()]
            net_dict[net_name] = (qty, profs_list)
        tgen_defs[internal_type] = net_dict

    return duration, analysis_window_size, networks, net_id_map, net_short, loss_profiles, hcs_nodes, hcs_profiles_by_channel, tgen_defs, hcs_channel_models

def distribute_profiles(qty, profiles):
    """Convert fractional profiles to discrete assignment list."""
    result = []
    remaining = qty
    for i, (prof, frac) in enumerate(profiles):
        if i == len(profiles) - 1:
            count = remaining
        else:
            count = round(qty * frac)
            remaining -= count
        for _ in range(count):
            result.append(prof)
    return result

# Network to DNS resolver mapping
NET_TO_DNS_NAME = {
    "client_net_mastodon":   "corpMasDns",
    "client_net_racetunnel": "corpRtDns",
    "client_net_iodine":     "corpIodDns",
    "client_net_obfs":       "corpObfsDns",
    "client_net_sky":        "corpSkyDns",
    "server_net":            "servDns",
}

def get_client_lst(hcs_client_ids):
    all_clients = []
    for i in hcs_client_ids["webtunnel"]: all_clients.append(f"wtCl{i}IrcAddr")
    for i in hcs_client_ids["skyhook"]: all_clients.append(f"skyCl{i}IrcAddr")
    for i in hcs_client_ids["obfs4"]: all_clients.append(f"obfsCl{i}IrcAddr")
    for i in hcs_client_ids["iodine"]: all_clients.append(f"iodCl{i}IrcAddr")
    for i in hcs_client_ids["mastodon"]: all_clients.append(f"masCl{i}IrcAddr")
    return all_clients

def get_corp_dns_addr_name(net):
    return NET_TO_DNS_NAME[net] + "Addr"

def link_param_name(net_name, dns=None):
    """Generate a Maude operator name for the link parameters of a network."""
    parts = net_name.split("_")
    camel = "".join(p.capitalize() for p in parts)
    if dns:
        return f"LinkType-{camel}-{dns}"
    return f"LinkType-{camel}"

class TgenInstance:
    def __init__(self, tgen_type, network, idx_in_net, profile, net_id, net_short):
        self.tgen_type = tgen_type   # "masTgen", "ftpTgen", "dnsTgen", "minTgen", "gorTgen", "ircTgen"
        self.network = network
        self.idx = idx_in_net        # 1-based index within this network+type
        self.profile = profile
        self.net_id = net_id         # NetId string, e.g. "cl[1]" or "srvN"
        
        ns = net_short[network]
        self.base_name = f"{tgen_type}{ns}{self.idx}"

def generate_all_tgen_instances(tgen_defs, net_id_map, net_short):
    """Generate all TGEN instances."""
    instances = []
    
    for tgen_type, tgen_networks in tgen_defs.items():
        for network, (qty, profiles) in tgen_networks.items():
            net_id = net_id_map[network]
            profile_list = distribute_profiles(qty, profiles)
            for i, prof in enumerate(profile_list):
                inst = TgenInstance(tgen_type, network, i + 1, prof, net_id, net_short)
                instances.append(inst)
                
    return instances

# Generate scenario1_addresses.maude
def gen_addresses_file(hcs_nodes, tgen_instances, net_id_map, scenario_name, notgens):
    lines = []
    L = lines.append
    
    L(f"--- MAUDE_HCS: this file is autogenerated for CP3 {scenario_name} ---")
    L("--- Address mapping: readable names   structured addresses")
    L("--- cl[N] refers to the NetId of the client network N")
    L("")
    
    mod_name = scenario_name.upper().replace("_", "-")
    L(f"mod {mod_name}-ADDRESSES is")
    L("  inc STRUCTURED-ADDRESSES .")
    L("")
    
    L("  ---------------------------------------------------")
    L("  --- HCS Node Addresses")
    L("  ---------------------------------------------------")
    
    L("  ops ircServerAddr s3SrvAddr ircMonitorAddr : -> Address .")
    L("  ops masSrvAddr masNetSrvAddr : -> Address .")
    L("  ops advAddr transportAddr : -> Address .")
    L("")

    hcs_client_ids = {
        "webtunnel" : [],
        "skyhook" : [],
        "obfs4" : [],
        "iodine" : [],
        "mastodon" : []
    }

    global_client_id = 1
    
    for channel, net_name, qty, profs in hcs_nodes:
        net_id = net_id_map[net_name]
        
        for idx in range(1, qty + 1):
            i = global_client_id
            
            if channel == "webtunnel":
                L(f"  --- Webtunnel Client {i} (Network {net_id}, index {idx})")
                L(f"  ops wtCl{i}IrcAddr wtCl{i}UmAddr wtCl{i}IfaceAddr wtCl{i}SrvIfaceAddr : -> Address .")
                L(f"  ops wtCl{i}ClientAddr wtCl{i}ProxyAddr : -> Address .")
                L(f"  ops wtCl{i}NetClientAddr wtCl{i}NetServerAddr : -> Address .")                
            elif channel == "skyhook":
                L(f"  --- Skyhook Client {i} (Network {net_id}, index {idx})")
                L(f"  ops skyCl{i}IrcAddr skyCl{i}UmAddr skyCl{i}IfaceAddr skyCl{i}SrvIfaceAddr : -> Address .")
                L(f"  ops skyCl{i}UmacAddr skyCl{i}CmacAddr skyCl{i}PuaAddr skyCl{i}SdkacAddr : -> Address .")
                L(f"  ops skyCl{i}UmasAddr skyCl{i}CmasAddr skyCl{i}AhaAddr skyCl{i}SdkasAddr : -> Address .")
                L(f"  ops skyCl{i}ClNetAddr skyCl{i}SrvNetClAddr skyCl{i}NetSrvAddr : -> Address .")
            elif channel == "obfs4":
                L(f"  --- OBFS4 Client {i} (Network {net_id}, index {idx})")
                L(f"  ops obfsCl{i}IrcAddr obfsCl{i}UmAddr obfsCl{i}IfaceAddr obfsCl{i}SrvIfaceAddr : -> Address .")
                L(f"  ops obfsCl{i}ClientAddr obfsCl{i}ServerAddr : -> Address .")
                L(f"  ops obfsCl{i}NetClientAddr obfsCl{i}NetServerAddr : -> Address .")
            elif channel == "iodine":
                L(f"  --- Iodine Client {i} (Network {net_id}, index {idx})")
                L(f"  ops iodCl{i}IrcAddr iodCl{i}UmAddr iodCl{i}IfaceAddr iodCl{i}SrvIfaceAddr : -> Address .")
                L(f"  ops iodCl{i}SendAppAddr iodCl{i}RcvAppAddr iodCl{i}ClientAddr iodCl{i}ServerAddr : -> Address .")
                L(f"  ops iodCl{i}NetServerAddr iodCl{i}SrvNetClAddr iodCl{i}SrvNetSrvAddr  : -> Address .")
            elif channel == "mastodon":
                L(f"  --- Mastodon HCS Client {i} (Network {net_id}, index {idx})")
                L(f"  ops masCl{i}IrcAddr masCl{i}UmAddr masCl{i}IfaceAddr masCl{i}SrvIfaceAddr : -> Address .")
                L(f"  ops masCl{i}UmacAddr masCl{i}CmacAddr masCl{i}McacAddr masCl{i}EdacAddr : -> Address .")
                L(f"  ops masCl{i}UmasAddr masCl{i}CmasAddr masCl{i}McasAddr masCl{i}EdasAddr : -> Address .")
                L(f"  ops masCl{i}ClNetAddr masCl{i}SrvNetClAddr : -> Address .")
            hcs_client_ids[channel].append(i)
            
            global_client_id += 1
            
        if qty > 0:
            L("")
    
    L("  --- DNS Infrastructure")
    L("  ops publicDnsAddr rootDnsAddr tldDnsAddr authDnsAddr : -> Address .")
    L("  ops corpMasDnsAddr corpRtDnsAddr corpIodDnsAddr corpObfsDnsAddr corpSkyDnsAddr : -> Address .")
    L("  ops servDnsAddr : -> Address .")
    L("  ops corpMasNetClAddr corpRtNetClAddr corpIodNetClAddr corpObfsNetClAddr corpSkyNetClAddr : -> Address .")
    L("  ops servNetClAddr publicResolverNetSrvAddr : -> Address .")
    L("")

    L("  ---------------------------------------------------")
    L("  --- TGEN Addresses")
    L("  ---------------------------------------------------")
    
    for inst in tgen_instances:
        bn = inst.base_name
        if inst.tgen_type == "masTgen":
            L(f"  ops {bn}UmAddr {bn}TgAddr {bn}McAddr : -> Address .")
            L(f"  ops {bn}NetClAddr : -> Address .")
        elif inst.tgen_type == "ftpTgen":
            L(f"  ops {bn}UmAddr {bn}TgAddr : -> Address .")
            L(f"  ops {bn}NetClAddr : -> Address .")
        elif inst.tgen_type == "dnsTgen":
            L(f"  ops {bn}UmAddr {bn}TgAddr : -> Address .")
        elif inst.tgen_type == "minTgen":
            L(f"  ops {bn}UmAddr {bn}TgAddr {bn}S3ClAddr : -> Address .")
            L(f"  ops {bn}NetClAddr : -> Address .")
        elif inst.tgen_type == "gorTgen":
            L(f"  ops {bn}UmAddr {bn}TgAddr : -> Address .")
            L(f"  ops {bn}NetClAddr : -> Address .")
        elif inst.tgen_type == "ircTgen":
            L(f"  ops {bn}UmAddr {bn}TgAddr : -> Address .")
            L(f"  ops {bn}NetClAddr : -> Address .")

    L("")
    L("  --- Shared TGEN Server Addresses")
    L("  ops ftpSrvAddr ftpNetSrvAddr : -> Address .")
    L("  ops gorillaSrvAddr gorillaNetSrvAddr : -> Address .")
    L("  ops ircTgenSrvNetAddr : -> Address .")
    L("")
    
    L("endm")
    
    return "\n".join(lines), hcs_client_ids

def resolver_for_network(network):
    """Use the source network's resolver; networks without one use public DNS."""
    return get_corp_dns_addr_name(network) if network in NET_TO_DNS_NAME else "publicDnsAddr"


def tcp_endpoint_policy(hcs_nodes, tgen_instances):
    """Map each actual TCP endpoint to its source network's resolver."""
    endpoints = {}
    prefixes = {"webtunnel": "wt", "skyhook": "sky", "obfs4": "obfs", "mastodon": "mas"}
    suffixes = {"webtunnel": ("ClientAddr", "ProxyAddr"),
                "skyhook": ("SdkacAddr", "SdkasAddr"),
                "obfs4": ("ClientAddr", "ServerAddr"),
                "mastodon": ("McacAddr", "McasAddr")}
    client_id = 1
    for channel, network, quantity, profiles in hcs_nodes:
        for _ in range(quantity):
            if channel in suffixes:
                base = f"{prefixes[channel]}Cl{client_id}"
                client, server = suffixes[channel]
                endpoints[base + client] = resolver_for_network(network)
                endpoints[base + server] = resolver_for_network("server_net")
            client_id += 1
    endpoints.update(tgen_tcp_endpoints(tgen_instances, resolver_for_network))
    # Shared servers may also initiate connections (e.g. Gorilla broadcasts).
    server_networks = {"s3SrvAddr": "minio_net", "masSrvAddr": "mastodon_net",
                       "ftpSrvAddr": "server_net", "gorillaSrvAddr": "server_net",
                       "ircServerAddr": "server_net"}
    for address, network in server_networks.items():
        endpoints[address] = resolver_for_network(network)
    return list(endpoints.items())


def emit_transport_module(L, mod_name, hcs_nodes, tgen_instances, transport_mode):
    """Keep transport policy separate from protocol message equations."""
    L(f"mod {mod_name}-TRANSPORT is")
    L("  pr TRANSPORT .")
    L(f"  inc {mod_name}-ADDRESSES .")
    L("  var requestId : Nat .")
    if transport_mode == "tcp":
        L("  --- WT/Obfs4 use a stable ID; Mastodon/S3 supply the request ID.")
        for address, resolver in tcp_endpoint_policy(hcs_nodes, tgen_instances):
            L(f"  eq transport({address}, requestId) = tcppersist({address}, requestId) .")
        L("  --- FTP and chat TGENs use one persistent connection per endpoint pair.")
        one_arg = set()
        servers = {"ftpTgen": "ftpSrvAddr", "gorTgen": "gorillaSrvAddr", "ircTgen": "ircServerAddr"}
        for inst in tgen_instances:
            if inst.tgen_type in servers:
                one_arg.add(servers[inst.tgen_type])
            if inst.tgen_type == "gorTgen":
                one_arg.add(inst.base_name + "TgAddr")
        for address in sorted(one_arg):
            L(f"  eq transport({address}) = tcppersist({address}, 0) .")
    L("endm")
    L("")


def emit_dns_policy_module(L, mod_name, hcs_nodes, tgen_instances):
    """The current Network Actor selects DNS by the connection's source address."""
    L(f"mod {mod_name}-TRANSPORT-DNS is")
    L("  inc NETWORK_NODE .")
    L(f"  inc {mod_name}-ADDRESSES .")
    L("  var netAttrs : AttributeSet .")
    for address, resolver in tcp_endpoint_policy(hcs_nodes, tgen_instances):
        L(f"  eq getDnsRsv(netAttrs, {address}) = {resolver} .")
    L("endm")
    L("")


SUPPORTED = {"ftpTgen", "gorTgen", "minTgen", "dnsTgen", "masTgen", "ircTgen"}


def _validate(instances):
    names = [inst.base_name for inst in instances]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate TGEN base names")
    for inst in instances:
        if inst.tgen_type not in SUPPORTED:
            raise ValueError(f"Unsupported configured TGEN: {inst.tgen_type}")


def emit_tgen_definitions(L, instances, resolver_for_network):
    """resolver_for_network(network) returns a Maude resolver Address string."""
    _validate(instances)
    types = {inst.tgen_type for inst in instances}
    L("  --- TGEN servers and application actors; transport is shared.")
    if "ftpTgen" in types:
        L("  op ftpSrvAct : -> Actor .")
        L("  eq ftpSrvAct = mkFtpServerA(ftpSrvAddr) .")
    if "gorTgen" in types:
        addresses = " addr ".join(inst.base_name + "TgAddr" for inst in instances
                                  if inst.tgen_type == "gorTgen")
        L("  op gorillaSrvAct : -> Actor .")
        L(f"  eq gorillaSrvAct = mkGorillaChatServer(gorillaSrvAddr, ({addresses})) .")
    # IRC, S3 and Mastodon servers already belong to the common infrastructure.
    for inst in instances:
        bn, profile = inst.base_name, inst.profile.replace("_", "-")
        kind = inst.tgen_type
        extra = {"minTgen": f" {bn}S3ClAct", "masTgen": f" {bn}McAct"}.get(kind, "")
        L(f"  --- {kind}: {bn}, profile={inst.profile}, network={inst.network}")
        L(f"  ops {bn}Act {bn}UmAct{extra} : -> Actor .")
        if kind == "ftpTgen":
            key = f"ftp-tgen-{profile}"
            L(f'  eq {bn}Act = mkFtpTgenA({bn}TgAddr, ftpSrvAddr, 5.0, 2, "{key}") .')
            L(f'  eq {bn}UmAct = mkTgenUMV2Actor({bn}UmAddr, "{key}", {bn}TgAddr) .')
        elif kind == "gorTgen":
            key = f"gorilla-tgen-{profile}"
            L(f"  eq {bn}Act = mkGorillaChatTgenA({bn}TgAddr, gorillaSrvAddr) .")
            L(f'  eq {bn}UmAct = mkTgenUMV2Actor({bn}UmAddr, "{key}", {bn}TgAddr) .')
        elif kind == "minTgen":
            key = f"minio-tgen-{profile}"
            L(f'  eq {bn}Act = mkMinioTgenA({bn}TgAddr, {bn}S3ClAddr, "tgen", "{key}") .')
            L(f"  eq {bn}S3ClAct = makeS3Client({bn}S3ClAddr, s3SrvAddr) .")
            L(f'  eq {bn}UmAct = mkTgenUMV2Actor({bn}UmAddr, "{key}", {bn}TgAddr) .')
        elif kind == "dnsTgen":
            model = f"dns-tgen-{profile}-ma"
            resolver = resolver_for_network(inst.network)
            L(f"  eq {bn}Act = mkDnsTgenA({bn}TgAddr, {resolver}, 1000, 5.0, 2) .")
            L(f"  eq {bn}UmAct = mkUMactor({bn}UmAddr, {model}, {bn}TgAddr) .")
        elif kind == "masTgen":
            model = f"mastodon-tgen-{profile}-ma"
            L(f"  eq {bn}Act = mkMasTGenActor({bn}TgAddr, {bn}McAddr, ed-images, {model}) .")
            L(f"  eq {bn}McAct = makeMastodonClient({bn}McAddr, masSrvAddr, {bn}TgAddr) .")
            L(f"  eq {bn}UmAct = mkUMactor({bn}UmAddr, {model}, {bn}TgAddr) .")
        elif kind == "ircTgen":
            key = f"irc-tgen-{profile}"
            L(f'  eq {bn}Act = mkIrcTgenClient({bn}TgAddr, transport(ircServerAddr), "{bn}") .')
            L(f'  eq {bn}UmAct = mkIrcUMV2Actor({bn}UmAddr, "{key}", {bn}TgAddr, transport(ircServerAddr), {bn}TgAddr) .')
        L("")


def emit_tgen_initial_actors(L, instances):
    _validate(instances)
    types = {inst.tgen_type for inst in instances}
    if "ftpTgen" in types:
        L("    ftpSrvAct")
    if "gorTgen" in types:
        L("    gorillaSrvAct")
    for inst in instances:
        bn = inst.base_name
        extra = {"minTgen": f" {bn}S3ClAct", "masTgen": f" {bn}McAct"}.get(inst.tgen_type, "")
        L(f"    {bn}UmAct {bn}Act{extra}")


def emit_tgen_start_timers(L, instances, timer_j, start_noise=0.009):
    """Return next unused RNG offset; assign it to timer_j before rCtr output."""
    _validate(instances)
    for inst in instances:
        bn = inst.base_name
        message = 'actionR("ok")' if inst.tgen_type in {"masTgen", "dnsTgen"} else "burstDelayTO"
        L(f"    [tgenDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), "
          f"(to {bn}UmAddr from {bn}UmAddr : {message}), 0]")
        timer_j += 1
    return timer_j


def tgen_tcp_endpoints(instances, resolver_for_network):
    """Return TGEN client address/resolver pairs for the endpoint DNS policy.

    MinIO and Mastodon use the HCS clients' two-argument transport API.
    FTP/Gorilla use one-argument transport: configure persistent ID 0 if enabled.
    IRC stores transport(ircServerAddr) as its upstream address because its
    sends do not call transport themselves. DNS TGEN is ordinary DNS.
    Do not register actor proxy/UM addresses as transport endpoints.
    """
    _validate(instances)
    endpoints = {}
    suffixes = {"ftpTgen": "TgAddr", "gorTgen": "TgAddr", "minTgen": "S3ClAddr", "masTgen": "McAddr", "ircTgen": "TgAddr"}
    for inst in instances:
        if inst.tgen_type in suffixes:
            endpoints[inst.base_name + suffixes[inst.tgen_type]] = resolver_for_network(inst.network)
    return list(endpoints.items())


# Generate the scenario module with readable endpoint addresses.
def gen_main_file(tgen_instances, networks, loss_profiles, hcs_profiles_by_channel, duration, hcs_channel_models, hcs_client_ids, hcs_nodes, scenario_name, net_id_map, hcs_delay, tgen_delay, vpts_list, perf=False, force_observer=False, notgens=False, features=None, transport_mode="tcp"):
    features = FEATURES if features is None else features
    lines = []
    L = lines.append
    
    L(f"--- MAUDE_HCS: CP3 {scenario_name} Experiment ---")
    L("--- Autogenerated from scenario YAML ---")
    L("")
    L("set clear rules off .")
    L("set print attribute off .")
    L("set show advisories off .")
    L("")
    
    L("--- Core Infrastructure")
    L(f"sload {GLOBALS.LIB_DIR}/webtunnel/webtunnel_prob.maude")
    L(f"sload {GLOBALS.LIB_DIR}/irc/irc_prob-v2")
    L(f"sload {GLOBALS.LIB_DIR}/irc/ircMonitor")
    L(f"sload {GLOBALS.LIB_DIR}/irc/irc-byteseq-interface")
    L(f"sload {GLOBALS.LIB_DIR}/common/maude/irc-action-actor-v2.maude")
    L(f"sload {GLOBALS.LIB_DIR}/irc/common/irc_name")
    L(f"sload {GLOBALS.LIB_DIR}/irc/common/_aux")
    L(f"sload {GLOBALS.LIB_DIR}/irc/common/app_chat")
    L(f"sload {GLOBALS.LIB_DIR}/irc/_irc_aux")
    L(f"sload {GLOBALS.DEPS_DIR}/dns_formalization/Maude/common/apmaude.maude")
    L(f"sload {GLOBALS.LIB_DIR}/obfs4/_obfs4_aux.maude")
    L(f"sload {GLOBALS.LIB_DIR}/obfs4/obfs4_prob.maude")
    L(f"sload {GLOBALS.LIB_DIR}/common/maude/user-action-actor")
    L(f"sload {GLOBALS.LIB_DIR}/raceboatMastodon/maude/enc-dec-actor.maude")
    L(f"sload {GLOBALS.LIB_DIR}/raceboatMastodonBidir/maude/rb-cm-bidir-mas.maude")
    L(f"sload {GLOBALS.LIB_DIR}/mastodon/maude/probabilistic/mastodon")
    
    if "mastodon" in hcs_channel_models:
        mas_client = hcs_channel_models["mastodon"]["client"]
        mas_server = hcs_channel_models["mastodon"]["server"]
        L(f"sload mastodon_action_models/{mas_client}.maude")
        L(f"sload mastodon_action_models/{mas_server}.maude")
    
    L(f"sload {GLOBALS.LIB_DIR}/common/maude/http-overhead.maude")
    
    if "skyhook" in hcs_channel_models:
        sky_client = hcs_channel_models["skyhook"]["client"]
        sky_server = hcs_channel_models["skyhook"]["server"]
        L(f"sload skyhook_action_models/{sky_client}.maude")
        L(f"sload skyhook_action_models/{sky_server}.maude")
    
    L(f"sload {GLOBALS.LIB_DIR}/irc/common/irc-msg-model")
    L(f"sload {GLOBALS.LIB_DIR}/raceboatSkyhook/maude/rb-cm-simple-bi")
    L(f"sload {GLOBALS.LIB_DIR}/skyhook/skyhook_prob")
    L(f"sload {GLOBALS.LIB_DIR}/s3/s3_protocol")
    L(f"sload {GLOBALS.LIB_DIR}/dns/maude/probabilistic/iodine_dns.maude")
    L(f"sload {GLOBALS.LIB_DIR}/dns/maude/common/_aux.maude")
    L(f"sload {GLOBALS.LIB_DIR}/network/net_prob.maude")
    L(f"sload {GLOBALS.LIB_DIR}/network/net-dns_prob.maude")
    L(f"sload {GLOBALS.LIB_DIR}/common/maude/structured-addresses.maude")
    L("")
    
    L("--- TGEN Actor Infrastructure")
    L(f"sload {GLOBALS.LIB_DIR}/common/maude/tgen-action-actor-v2.maude")
    L(f"sload {GLOBALS.LIB_DIR}/tgen/maude/ftp/ftpTgen-actor.maude")
    L(f"sload {GLOBALS.LIB_DIR}/tgen/maude/ftp/ftpServer-actor.maude")
    L(f"sload {GLOBALS.LIB_DIR}/tgen/maude/gorillachat/gorilla-Tgen-actor.maude")
    L(f"sload {GLOBALS.LIB_DIR}/tgen/maude/minio/minioTgen-actor.maude")
    L(f"sload {GLOBALS.LIB_DIR}/s3/s3_protocol.maude")
    L(f"sload {GLOBALS.LIB_DIR}/tgen/maude/dnsTgen-actor-uniqueId.maude")
    L(f"sload {GLOBALS.LIB_DIR}/tgen/maude/masTGen.maude")
    L(f"sload {GLOBALS.LIB_DIR}/tgen/maude/irc/ircTgen-actor.maude")
    L("")
    
    L("--- HCS IRC User Models (v2)")
    hcs_irc_profiles_needed = set()
    for channel, profs in hcs_profiles_by_channel.items():
        for p, _ in profs:
            hcs_irc_profiles_needed.add(p)
    for p in sorted(hcs_irc_profiles_needed):
        L(f"sload irc_user_models/{p}.maude")
    L("")
    
    L("--- IRC TGEN Profiles (v2)")
    tgen_irc_profiles_needed = set()
    for inst in tgen_instances:
        if inst.tgen_type == "ircTgen":
            tgen_irc_profiles_needed.add(inst.profile)
    for p in sorted(tgen_irc_profiles_needed):
        L(f"sload tgen_user_models/irc/{p}.maude")
    L("")
    
    L("--- FTP TGEN Profiles (v2)")
    ftp_profiles = set()
    for inst in tgen_instances:
        if inst.tgen_type == "ftpTgen":
            ftp_profiles.add(inst.profile)
    for p in sorted(ftp_profiles):
        L(f"sload tgen_user_models/ftp/{p}.maude")
    L("")
    
    L("--- MinIO TGEN Profiles (v2)")
    minio_profiles = set()
    for inst in tgen_instances:
        if inst.tgen_type == "minTgen":
            minio_profiles.add(inst.profile)
    for p in sorted(minio_profiles):
        L(f"sload tgen_user_models/minio/{p}.maude")
    L("")
    
    L("--- Gorilla TGEN Profiles (v2)")
    gorilla_profiles = set()
    for inst in tgen_instances:
        if inst.tgen_type == "gorTgen":
            gorilla_profiles.add(inst.profile)
    for p in sorted(gorilla_profiles):
        L(f"sload tgen_user_models/gorilla/{p}.maude")
    L("")
    
    L("--- DNS TGEN Profiles (v1)")
    dns_profiles = set()
    for inst in tgen_instances:
        if inst.tgen_type == "dnsTgen":
            dns_profiles.add(inst.profile)
    for p in sorted(dns_profiles):
        L(f"sload tgen_user_models/dns/{p}.maude")
    L("")
    
    L("--- Mastodon TGEN Profiles (v1)")
    mas_profiles = set()
    for inst in tgen_instances:
        if inst.tgen_type == "masTgen":
            mas_profiles.add(inst.profile)
    for p in sorted(mas_profiles):
        L(f"sload tgen_user_models/mastodon/{p}.maude")
    L("")

    L("--- Address mapping")
    L(f"sload {scenario_name}_addresses")
    L("")
    
    L("--- Visibility map (needed for SMC)")
    L(f"sload {GLOBALS.LIB_DIR}/smc/visibility-plain")
    L("")

    L("--- load the baseline actor (simplifies how we add baseline data)")
    L(f"sload {GLOBALS.LIB_DIR}/smc/smc-baseline-shared")
    L(f"sload {GLOBALS.LIB_DIR}/smc-baseline/baseline-actor")
    L("")

    mod_name = scenario_name.upper().replace("_", "-")
    emit_transport_module(L, mod_name, hcs_nodes, tgen_instances, transport_mode)
    emit_dns_policy_module(L, mod_name, hcs_nodes, tgen_instances)
    L(f"mod {mod_name} is")
    L(f"  inc {mod_name}-TRANSPORT .")
    L(f"  inc {mod_name}-TRANSPORT-DNS .")
    L("  pr SCHEDULER .")
    L("  pr USER-ACTION-ACTOR .")
    if "skyhook" in hcs_channel_models:
        sky_client = hcs_channel_models["skyhook"]["client"]
        sky_server = hcs_channel_models["skyhook"]["server"]
        L(f"  inc SKYHOOK-{sky_client.upper().replace('_', '-')}-MAMODEL .")
        L(f"  inc SKYHOOK-{sky_server.upper().replace('_', '-')}-MAMODEL .")

    L("  pr IRC-V2 .")
    L("  pr IRC-USER-ACTION-ACTOR-V2 .")
    L("  pr IRC-BYTESEQ-INTERFACE .")
    L("  pr CONTENT-MANAGER-SIMPLE-BI .")
    L("  inc ENC-DEC .")
    L("  inc CONTENT-MANAGER-BIDIR .")
    L("  inc MASTODON .")

    if "mastodon" in hcs_channel_models:
        mas_client = hcs_channel_models["mastodon"]["client"]
        mas_server = hcs_channel_models["mastodon"]["server"]
        L(f"  inc MASTODON-{mas_client.upper().replace('_', '-')}-MAMODEL .")
        L(f"  inc MASTODON-{mas_server.upper().replace('_', '-')}-MAMODEL .")
    L("  pr SKYHOOK .")
    L("  pr S3_PROTOCOL .")
    L("  pr IRC_MONITOR .")
    L("  pr OBFS4 .")
    L("  pr APP_CHATS .")
    L("  pr IRC_NODE .")
    L("  pr WEBTUNNEL .")
    L("  pr IRC_NAMES .")
    L("  pr IODINE_NODE .")
    L("  pr IODINE_DNS .")
    L("  pr TCP_SOCKET .")
    L("  pr NET-DNS .")
    L("  pr NETWORK_NODE .")
    L("  pr NETWORK_CONNECTION .")
    L("  inc STRUCTURED-ADDRESSES .")    
    L("  --- include autogenerated addresses")
    L(f"  inc {mod_name}-ADDRESSES .")
    L("")    
    L("  --- TGEN Modules")
    L("  inc USER-ACTION-ACTOR-V2 .")
    L("  inc FTP-TGEN .")
    L("  inc FTP-SERVER .")
    L("  inc GORILLACHAT-TGEN .")
    L("  inc MINIO-TGEN .")
    L("  inc DNS-TGEN .")
    L("  inc MAS-TGEN .")
    L("  inc IRC-TGEN .")
    L("")
    
    L("  --- HCS IRC Profile Modules")
    for p in sorted(hcs_irc_profiles_needed):
        mod = f"IRC-{p.upper().replace('_', '-')}-MAMODEL-V2"
        L(f"  inc {mod} .")
    L("")
    
    L("  --- IRC TGEN Profile Modules")
    for p in sorted(tgen_irc_profiles_needed):
        mod = f"IRC-TGEN-{p.upper().replace('_', '-')}-MAMODEL-V2"
        L(f"  inc {mod} .")
    L("")
    
    L("  --- FTP Profile Modules")
    for p in sorted(ftp_profiles):
        mod = f"FTP-TGEN-{p.upper().replace('_', '-')}-MAMODEL-V2"
        L(f"  inc {mod} .")
    L("")
    
    L("  --- MinIO Profile Modules")
    for p in sorted(minio_profiles):
        mod = f"MINIO-TGEN-{p.upper().replace('_', '-')}-MAMODEL-V2"
        L(f"  inc {mod} .")
    L("")
    
    L("  --- Gorilla Profile Modules")
    for p in sorted(gorilla_profiles):
        mod = f"GORILLA-TGEN-{p.upper().replace('_', '-')}-MAMODEL-V2"
        L(f"  inc {mod} .")
    L("")
    
    L("  --- DNS Profile Modules (v1)")
    for p in sorted(dns_profiles):
        mod = f"DNS-TGEN-{p.upper().replace('_', '-')}-MAMODEL"
        L(f"  inc {mod} .")
    L("")
    
    L("  --- Mastodon TGEN Profile Modules (v1)")
    for p in sorted(mas_profiles):
        mod = f"MASTODON-TGEN-{p.upper().replace('_', '-')}-MAMODEL"
        L(f"  inc {mod} .")
    L("")
    
    L("  --- Visibility map")
    L("  inc VISIBILITY .")
    L("")
    
    L("  --- Baseline actor")
    L("  inc SMC-BASELINE-SHARED .")
    L("  inc BASELINE-ACTOR .")
    L("")

    L("  vars j : Nat .")
    L("")
    
    L("  ---------------------------------------------------")
    L("  --- Global Constants")
    L("  ---------------------------------------------------")
    L("  eq encOH(fsize:Nat,ksize:Nat) = 0 .")
    L("  eq noiseMin(msg:Msg)          = 0.00001 .")
    L("  eq noiseMax(msg:Msg)          = 0.001 .")
    L("  eq maxMinimiseCount           = 0 .")
    L("  eq packetSize                 = 1000 .")
    L("  eq maxPacketSize              = 1000 .")
    L("  eq maxUpFragmentLen = 71 .")
    L("  eq maxDownFragmentLen = 200 .")
    logger.warning("TODO: extract and set Iodine packet size and framgment size correctly")
    
    L("  --- how much to delay the HCS and TGENs")
    L("  ops hcsDelay tgenDelay ksWindowDelay : -> Float .")
    L(f"  eq hcsDelay  = {hcs_delay:.1f} [owise] .")
    L(f"  eq tgenDelay = {tgen_delay:.1f} [owise] .")
    L(f"  eq ksWindowDelay = slimit + slimit [owise] .")
    L(f"  eq MaxBLSize = {MAX_BL_SIZE} [owise] .")
    L("")
    L("  ----- SMC confidentiality parameters ----")
    L("  eq sT = 0.0 .")
    L("  eq wS =  60. .")
    L("  eq bS = 10. .")
    L("  eq eT = slimit .")
    L("")
    L("  *** op Vpts : -> NetIdList .")
    
    L(f"  eq Vpts = ({' :; '.join(vpts_list)}) [owise] .")
    L("")
    L("  *** op ObsFs : -> FeatureList .")
    L("  eq ObsFs = ")
    joined_features = " :; ".join(features)
    L((f"  {joined_features}"))    
    L("  [owise]")
    L("  .")
    L("  ----------------")
    L("")
    
    L("  --- User Model Database (MAModelMap)")
    mm_entries = []
    for p in sorted(hcs_irc_profiles_needed):
        key = f"irc-{p.replace('_', '-')}"
        op_name = f"irc-{p.replace('_', '-')}-ma-v2"
        mm_entries.append(f'"{key}" |-> {op_name}')
    for p in sorted(tgen_irc_profiles_needed):
        key = f"irc-tgen-{p.replace('_', '-')}"
        op_name = f"irc-tgen-{p.replace('_', '-')}-ma-v2"
        mm_entries.append(f'"{key}" |-> {op_name}')
    for p in sorted(ftp_profiles):
        key = f"ftp-tgen-{p.replace('_', '-')}"
        op_name = f"ftp-tgen-{p.replace('_', '-')}-ma-v2"
        mm_entries.append(f'"{key}" |-> {op_name}')
    for p in sorted(minio_profiles):
        key = f"minio-tgen-{p.replace('_', '-')}"
        op_name = f"minio-tgen-{p.replace('_', '-')}-ma-v2"
        mm_entries.append(f'"{key}" |-> {op_name}')
    for p in sorted(gorilla_profiles):
        key = f"gorilla-tgen-{p.replace('_', '-')}"
        op_name = f"gorilla-tgen-{p.replace('_', '-')}-ma-v2"
        mm_entries.append(f'"{key}" |-> {op_name}')
        
    if len(mm_entries) == 0:
        L("  eq MAModelMap = empty .")
    else:
        L("  eq MAModelMap =")
        if len(mm_entries) == 1:
            L(f"    ({mm_entries[0]})")
        else:
            for i, entry in enumerate(mm_entries):
                if i == 0:
                    L(f"    ({entry},")
                elif i == len(mm_entries) - 1:
                    L(f"     {entry})")
                else:
                    L(f"     {entry},")
        L("  .")
    L("")
    
    L("  op ed-images : -> ByteSeqL .")    
    preamble = " :: "
    L("  eq ed-images =")    
    for i in range(10):
        L(f"    {preamble if i > 0 and i < 10 else ' '}image({i+1}, {IMAGE_SIZE}, 3000)")
    L("  .")
    L("")
    
    L("  ---------------------------------------------------")
    L("  --- DNS Zone Configurations")
    L("  ---------------------------------------------------")
    L("  op zone : -> List{Record} .")
    L("  eq zone =")
    L("    < root, soa, 360000.0, soaData(360000.0) >")
    L("    < root, ns, 360000.0, 'a . 'root-servers . 'net . root >")
    L("    < 'a . 'root-servers . 'net . root, a, 360000.0, rootDnsAddr >")
    L("    < 'com . root, ns, 360000.0, 'ns . 'com . root >")
    L("    < 'ns . 'com . root, a, 360000.0, tldDnsAddr >")
    L("  .")
    L("")
    
    L("  op zoneCom : -> List{Record} .")
    L("  eq zoneCom =")
    L("    < 'com . root, soa, 360000.0, soaData(360000.0) >")
    L("    < 'com . root, ns, 360000.0, 'ns . 'com . root >")
    L("    < 'ns . 'com . root, a, 360000.0, tldDnsAddr >")
    L("    < 'pwnd . 'com . root, ns, 360000.0, 'ns . 'pwnd . 'com . root >")
    L("    < 'ns . 'pwnd . 'com . root, a, 360000.0, authDnsAddr >")
    L("    < 'i . 'com . root, ns, 360000.0, 'ns . 'i . 'com . root >")
    L("    < 'ns . 'i . 'com . root, a, 360000.0, authDnsAddr >")
    for dns_name, corp_dns_addr in [
        ("corpMas", "corpMasDnsAddr"), ("corpRt", "corpRtDnsAddr"),
        ("corpIod", "corpIodDnsAddr"), ("corpObfs", "corpObfsDnsAddr"),
        ("corpSky", "corpSkyDnsAddr")
    ]:
        zone_label = dns_name.lower().replace("corp", "")
        L(f"    < '{zone_label} . 'com . root, ns, 360000.0, 'ns . '{zone_label} . 'com . root >")
        L(f"    < 'ns . '{zone_label} . 'com . root, a, 360000.0, {corp_dns_addr} >")
    L("    < 'serv . 'com . root, ns, 360000.0, 'ns . 'serv . 'com . root >")
    L("    < 'ns . 'serv . 'com . root, a, 360000.0, servDnsAddr >")
    L("  .")
    L("")

    # create as many ns records and names for pwnd.com as there are iodine clients
    L("  op zoneInternetCom : -> List{Record} .")
    L("  eq zoneInternetCom =")
    L("    < 'i . 'com . root, soa, 360000.0, soaData(360000.0) >")
    L("    < 'i . 'com . root, ns, 360000.0, 'ns . 'i . 'com . root >")
    L("    < 'ns . 'i . 'com . root, a, 360000.0, authDnsAddr >")
    L("    < 'tmp0 . 'i . 'com . root, a, 0.0, 1 . 0 . 1 . 2 >")
    L("    < wildcard . 'i . 'com . root, a, 0.0, 1 . 1 . 1 . 2 >")
    L("  .")
    L("")
    L("  --- Shared transport lookup and Iodine delegations belong to pwnd.com.")
    L("  op zonePwndCom : -> List{Record} .")
    L("  eq zonePwndCom =")
    L("    < 'pwnd . 'com . root, soa, 360000.0, soaData(360000.0) >")
    L("    < 'pwnd . 'com . root, ns, 360000.0, 'ns . 'pwnd . 'com . root >")
    L("    < 'ns . 'pwnd . 'com . root, a, 360000.0, authDnsAddr >")
    L("    < 'mastodon . 'pwnd . 'com . root, a, 0.0, masSrvAddr >")
    for idx, clid in enumerate(hcs_client_ids["iodine"]):
        L(f"    < 't{idx+1} . 'pwnd . 'com . root, ns, 360000.0, 'ns . 't{idx+1} . 'pwnd . 'com . root >")
        L(f"    < 'ns . 't{idx+1} . 'pwnd . 'com . root, a, 360000.0, iodCl{clid}SrvNetClAddr >")
    L("  .")
    L("")
    

    L("  --- placeholder zone never exercised because iodineSvr never receives non weird names")
    L(f"  op zonePwndDef : -> List{{Record}} .")
    L(f"  eq zonePwndDef =")
    L(f"    < 'pwnd . 'com . root, soa, 360000.0, soaData(360000.0) > .")
    L("")
        
    for zone_label, dns_addr in [
        ("mas", "corpMasDnsAddr"), ("rt", "corpRtDnsAddr"),
        ("iod", "corpIodDnsAddr"), ("obfs", "corpObfsDnsAddr"),
        ("sky", "corpSkyDnsAddr"), ("serv", "servDnsAddr")
    ]:
        L(f"  op zone{zone_label.capitalize()}Com : -> List{{Record}} .")
        L(f"  eq zone{zone_label.capitalize()}Com =")
        L(f"    < '{zone_label} . 'com . root, soa, 360000.0, soaData(360000.0) >")
        L(f"    < '{zone_label} . 'com . root, ns, 360000.0, 'ns . '{zone_label} . 'com . root >")
        L(f"    < 'ns . '{zone_label} . 'com . root, a, 360000.0, {dns_addr} >")
        L(f"    < 'tmp0 . '{zone_label} . 'com . root, a, 0.0, 3 . 0 . 1 . 2 >")
        L(f"    < wildcard . '{zone_label} . 'com . root, a, 0.0, 3 . 1 . 1 . 2 >")
        L(f"  .")
        L("")
        
    L("  op sb : -> ZoneState .")
    L("  eq sb = < root ('a . 'root-servers . 'net . root |-> rootDnsAddr) > .")
    L("")
    
    L("  op resolverCache : -> Cache .")
    L("  eq resolverCache =")
    L("    cacheEntry(< root, ns, 360000.0, 'a . 'root-servers . 'net . root >, 1)")
    L("    cacheEntry(< 'a . 'root-servers . 'net . root, a, 360000.0, rootDnsAddr >, 1)")
    L("    cacheEntry(< 'com . root, ns, 360000.0, 'ns . 'com . root >, 1)")
    L("    cacheEntry(< 'ns . 'com . root, a, 360000.0, tldDnsAddr >, 1)")
    L("    cacheEntry(< 'pwnd . 'com . root, ns, 360000.0, 'ns . 'pwnd . 'com . root >, 1)")
    L("    cacheEntry(< 'ns . 'pwnd . 'com . root, a, 360000.0, authDnsAddr >, 1)")
    L("    cacheEntry(< 'i . 'com . root, ns, 360000.0, 'ns . 'i . 'com . root >, 1)")
    L("    cacheEntry(< 'ns . 'i . 'com . root, a, 360000.0, authDnsAddr >, 1)")
    for idx,clid in enumerate(hcs_client_ids["iodine"]):
        L(f"    cacheEntry(< 't{idx+1} . 'pwnd . 'com . root, ns, 360000.0, 'ns . 't{idx+1} . 'pwnd . 'com . root >, 1)")
        L(f"    cacheEntry(< 'ns . 't{idx+1} . 'pwnd . 'com . root, a, 360000.0, iodCl{clid}SrvNetClAddr >, 1)")        
    for zone_label, dns_addr in [
        ("mas", "corpMasDnsAddr"), ("rt", "corpRtDnsAddr"),
        ("iod", "corpIodDnsAddr"), ("obfs", "corpObfsDnsAddr"),
        ("sky", "corpSkyDnsAddr"), ("serv", "servDnsAddr")
    ]:
        L(f"    cacheEntry(< '{zone_label} . 'com . root, ns, 360000.0, 'ns . '{zone_label} . 'com . root >, 1)")
        L(f"    cacheEntry(< 'ns . '{zone_label} . 'com . root, a, 360000.0, {dns_addr} >, 1)")
    L("  .")
    L("")
    
    L("  ---------------------------------------------------")
    L("  --- Link Model Parameters")
    L("  --- One TCP link and one DNS link per net and one DNS composed link")
    L("  ---------------------------------------------------")

    def linkdata(F, _op_name, _lp, _onewaydelay, v1=False):
        """Emit lossless current TCP/DNS link attributes with the scenario delay."""
        F(f"  op {_op_name} : -> AttributeSet .")
        F(f"  eq {_op_name} =")
        if v1:
            F('    (delayStd: 0.0, delayType: "Constant",')
            F(f"     delayMean: {_onewaydelay}, delayConst: {_onewaydelay},")
            F("     noiseMin: 0.0, noiseMax: 0.00001,")
            F(f"     oneWayDelay: {_onewaydelay}, dropP: 0.0, canDrop: false) .")
        else:
            F(f"    (oneWayDelay: {_onewaydelay}, dropP: 0.0, canDrop: false) .")
        F("")

    DEF_LP = {"p13": 0.0, "p31": 1.0, "p32": 0.0, "p23": 0.0, "p14": 0.0}
    dns_net_latency_ms, dns_net_loss_profile = networks["dns_net"]
    for net_name, (latency_ms, loss_profile_name) in networks.items():
        if not loss_profile_name in loss_profiles:
            logger.warning('Loss profile %s does exists, reverting to default', loss_profile_name)
        lp = loss_profiles[loss_profile_name]
        ld_dns = loss_profiles[dns_net_loss_profile]
        one_way_delay = latency_ms / 1000.0
        one_way_delay_dns = dns_net_latency_ms / 1000.0
        op_name = link_param_name(net_name)
        op_name_dns = link_param_name(net_name, dns="Dns")
        op_name_dns_comp = link_param_name(net_name, dns="DnsComposed")
        # TCP link
        L(f"  --- TCP link from/to {net_name} to IXP")
        linkdata(L, op_name, lp, one_way_delay)
        # DNS link
        L(f"  --- DNS link from/to {net_name} to IXP")
        linkdata(L, op_name_dns, DEF_LP, one_way_delay, v1=True)
        # DNS composed link
        if net_name != "dns_net":
            L(f"  --- DNS composed link from/to {net_name} to dns_net")
            linkdata(L, op_name_dns_comp, DEF_LP, (latency_ms + dns_net_latency_ms) / 1000.0,  v1=True)
    
    L("  ---------------------------------------------------")
    L("  --- Link Data (Readable Addresses Only)")
    L("  ---------------------------------------------------")
    L("  eq LinkData =")
    
    link_entries = []
    
    # Store visible addresses per network (mapped by network name config string)
    vis_map = {net_name: [] for net_name in net_id_map.keys()}
    
    def add_bidir_link(addr1, addr2, link_type, src_net_name):
        link_entries.append(f"    aaa({addr1}, {addr2}, {link_type})")
        link_entries.append(f"    aaa({addr2}, {addr1}, {link_type})")
        # Add to visibility maps based on composed link rule: src address to source net, destination address to dns_net
        if src_net_name in vis_map and addr1 not in vis_map[src_net_name]:
            vis_map[src_net_name].append(addr1)
        if "dns_net" in vis_map and addr2 not in vis_map["dns_net"]:
            vis_map["dns_net"].append(addr2)
            
    def add_bidir_ixp(addr1, link_type, net_name):
        link_entries.append(f"    aaa({addr1}, IXP-DEFAULT-ADDR, {link_type})")
        link_entries.append(f"    aaa(IXP-DEFAULT-ADDR, {addr1}, {link_type})")
        # Add to visibility maps based on direct IXP rule: network's own address to that network
        if net_name in vis_map and addr1 not in vis_map[net_name]:
            vis_map[net_name].append(addr1)

    """
    We also add links between these actors ?
    corpMasNetClAddr
    corpRtNetClAddr
    corpObfsNetClAddr
    corpIodNetClAddr
    corpSkyNetClAddr
    corpRtDnsAddr
    ...
     <>
    publicResolverNetSrvAddr    (composed)
    publicDnsAddr (composed)
    IXP
    """
    server_net_link = link_param_name("server_net")
    server_net_link_dns = link_param_name("server_net", dns="Dns")
    server_net_link_dns_comp = link_param_name("server_net", dns="DnsComposed")
    dns_net_link_dns = link_param_name("dns_net", dns="Dns")
    minio_net_link = link_param_name("minio_net") if "minio_net" in networks else None
    mas_net_link = link_param_name("mastodon_net") if "mastodon_net" in networks else None

    if "client_net_racetunnel" in networks:
        wt_link = link_param_name("client_net_racetunnel")
        wt_link_dns = link_param_name("client_net_racetunnel", "Dns")
        wt_link_dns_comp = link_param_name("client_net_racetunnel", "DnsComposed")
        for i in hcs_client_ids["webtunnel"]:
            link_entries.append(f"    --- Webtunnel Client {i}")
            add_bidir_ixp(f"wtCl{i}ClientAddr", wt_link, "client_net_racetunnel")
            add_bidir_ixp(f"wtCl{i}ProxyAddr", server_net_link, "server_net")
        link_entries.append(f"    --- Webtunnel corp")
        add_bidir_ixp(f"corpRtNetClAddr", wt_link_dns, "client_net_racetunnel")
        add_bidir_link(f"corpRtNetClAddr", f"publicResolverNetSrvAddr", wt_link_dns_comp, "client_net_racetunnel")
        add_bidir_link(f"corpRtNetClAddr", f"publicDnsAddr", wt_link_dns_comp, "client_net_racetunnel")
        add_bidir_ixp(f"corpRtDnsAddr", wt_link_dns, "client_net_racetunnel")    
        add_bidir_link(f"corpRtDnsAddr", f"publicDnsAddr", wt_link_dns_comp, "client_net_racetunnel")
        link_entries.append("")
    
    if "client_net_obfs" in networks:
        obfs_link = link_param_name("client_net_obfs")
        obfs_link_dns = link_param_name("client_net_obfs", dns="Dns")
        obfs_link_dns_comp = link_param_name("client_net_obfs", dns="DnsComposed")
        for i in hcs_client_ids["obfs4"]:
            link_entries.append(f"    --- OBFS4 Client {i}")
            add_bidir_ixp(f"obfsCl{i}ClientAddr", obfs_link, "client_net_obfs")
            add_bidir_ixp(f"obfsCl{i}ServerAddr", server_net_link, "server_net")
        link_entries.append(f"    --- Obfs4 corp")
        add_bidir_ixp(f"corpObfsNetClAddr", obfs_link_dns, "client_net_obfs")
        add_bidir_link(f"corpObfsNetClAddr", f"publicResolverNetSrvAddr", obfs_link_dns_comp, "client_net_obfs")
        add_bidir_link(f"corpObfsNetClAddr", f"publicDnsAddr", obfs_link_dns_comp, "client_net_obfs")
        add_bidir_ixp(f"corpObfsDnsAddr", obfs_link_dns, "client_net_obfs")    
        add_bidir_link(f"corpObfsDnsAddr", f"publicDnsAddr", obfs_link_dns_comp, "client_net_obfs")
        link_entries.append("")
    
    if "client_net_sky" in networks:
        sky_link = link_param_name("client_net_sky")
        sky_link_dns = link_param_name("client_net_sky", dns="Dns")
        sky_link_dns_comp = link_param_name("client_net_sky", dns="DnsComposed")
        for i in hcs_client_ids["skyhook"]:
            link_entries.append(f"    --- Skyhook Client {i}")
            add_bidir_ixp(f"skyCl{i}SdkacAddr", sky_link, "client_net_sky")
            add_bidir_ixp(f"skyCl{i}SdkasAddr", server_net_link, "server_net")
        add_bidir_ixp(f"corpSkyNetClAddr", sky_link_dns, "client_net_sky")
        add_bidir_link(f"corpSkyNetClAddr", f"publicResolverNetSrvAddr", sky_link_dns_comp, "client_net_sky")
        add_bidir_link(f"corpSkyNetClAddr", f"publicDnsAddr", sky_link_dns_comp, "client_net_sky")    
        add_bidir_ixp(f"corpSkyDnsAddr", sky_link_dns, "client_net_sky")    
        add_bidir_link(f"corpSkyDnsAddr", f"publicDnsAddr", sky_link_dns_comp, "client_net_sky")
        link_entries.append("")

    link_entries.append("    --- Minio/S3 server")    
    add_bidir_ixp("s3SrvAddr", minio_net_link, "minio_net")
    link_entries.append("")

    if "client_net_mastodon" in networks:
        mas_link = link_param_name("client_net_mastodon")
        mas_link_dns = link_param_name("client_net_mastodon", dns="Dns")
        mas_link_dns_comp = link_param_name("client_net_mastodon", dns="DnsComposed")
        for i in hcs_client_ids["mastodon"]:    
            link_entries.append(f"    --- Mastodon HCS Client {i}")
            add_bidir_ixp(f"masCl{i}McacAddr", mas_link, "client_net_mastodon")
            add_bidir_ixp(f"masCl{i}McasAddr", server_net_link, "server_net")
        if "mastodon_net" in networks:
            link_entries.append("    --- Mastodon server")
            add_bidir_ixp("masSrvAddr", mas_net_link, "mastodon_net")
        add_bidir_ixp(f"corpMasNetClAddr", mas_link_dns, "client_net_mastodon")
        add_bidir_link(f"corpMasNetClAddr", f"publicResolverNetSrvAddr", mas_link_dns_comp, "client_net_mastodon")
        add_bidir_link(f"corpMasNetClAddr", f"publicDnsAddr", mas_link_dns_comp, "client_net_mastodon")
        add_bidir_ixp(f"corpMasDnsAddr", mas_link_dns, "client_net_mastodon")    
        add_bidir_link(f"corpMasDnsAddr", f"publicDnsAddr", mas_link_dns_comp, "client_net_mastodon")
        link_entries.append("")
    
    if "client_net_iodine" in networks:
        iod_link_dns = link_param_name("client_net_iodine", dns="Dns")
        iod_link_dns_comp = link_param_name("client_net_iodine", dns="DnsComposed")
        for i in hcs_client_ids["iodine"]:
            link_entries.append(f"    --- Iodine Client {i}")        
            # add_bidir_ixp(f"iodCl{i}ClientAddr", iod_link_dns, "client_net_iodine") # we removed this because iodine client uses the forwarder
            add_bidir_ixp(f"iodCl{i}ServerAddr", server_net_link_dns, "server_net")
            add_bidir_ixp(f"iodCl{i}SrvNetSrvAddr", server_net_link_dns, "server_net")
            add_bidir_ixp(f"iodCl{i}SrvNetClAddr", dns_net_link_dns, "dns_net")
            add_bidir_link(f"iodCl{i}SrvNetClAddr", f"iodCl{i}SrvNetSrvAddr", server_net_link_dns_comp, "server_net")
            add_bidir_link(f"iodCl{i}ServerAddr", "publicDnsAddr", server_net_link_dns_comp, "server_net")
            # netDnsSrvResponse schedules from the nameserver to the DNS-side
            # relay, rather than from the server-side relay address.
            link_entries.append(f"    aaa(iodCl{i}ServerAddr, iodCl{i}SrvNetClAddr, {server_net_link_dns_comp})")
            
        add_bidir_ixp(f"corpIodNetClAddr", iod_link_dns, "client_net_iodine")
        add_bidir_link(f"corpIodNetClAddr", f"publicResolverNetSrvAddr", iod_link_dns_comp, "client_net_iodine")
        add_bidir_link(f"corpIodNetClAddr", f"publicDnsAddr", iod_link_dns_comp, "client_net_iodine")    
        add_bidir_ixp("corpIodDnsAddr", iod_link_dns, "client_net_iodine")    
        add_bidir_link(f"corpIodDnsAddr", f"publicDnsAddr", iod_link_dns_comp, "client_net_iodine")
        link_entries.append("")

    add_bidir_ixp(f"servDnsAddr", server_net_link_dns, "server_net")        
    add_bidir_link(f"servDnsAddr", f"publicDnsAddr", server_net_link_dns_comp, "server_net")
    # add_bidir_ixp(f"servNetClAddr", server_net_link_dns)
    add_bidir_link(f"servNetClAddr", f"publicResolverNetSrvAddr", server_net_link_dns_comp, "server_net")
    add_bidir_link(f"servNetClAddr", f"publicDnsAddr", server_net_link_dns_comp, "server_net")
        

    add_bidir_ixp("publicDnsAddr", dns_net_link_dns, "dns_net")
    link_entries.append("")

    add_bidir_ixp("ircServerAddr", server_net_link, "server_net")
    link_entries.append("")

    link_entries.append("    --- TGEN Direct Links")
    
    # masTgen Mc
    for inst in tgen_instances:
        if inst.tgen_type == "masTgen":
            add_bidir_ixp(f"{inst.base_name}McAddr", link_param_name(inst.network), inst.network)
    link_entries.append("")
    
    # ftpTgen Tg
    for inst in tgen_instances:
        if inst.tgen_type == "ftpTgen":
            add_bidir_ixp(f"{inst.base_name}TgAddr", link_param_name(inst.network), inst.network)
    link_entries.append("")
    
    # minTgen S3
    for inst in tgen_instances:
        if inst.tgen_type == "minTgen":
            add_bidir_ixp(f"{inst.base_name}S3ClAddr", link_param_name(inst.network), inst.network)
    link_entries.append("")
    
    # gorTgen Tg
    for inst in tgen_instances:
        if inst.tgen_type == "gorTgen":
            add_bidir_ixp(f"{inst.base_name}TgAddr", link_param_name(inst.network), inst.network)
    link_entries.append("")
    
    # ircTgen Tg
    for inst in tgen_instances:
        if inst.tgen_type == "ircTgen":
            add_bidir_ixp(f"{inst.base_name}TgAddr", link_param_name(inst.network), inst.network)
    link_entries.append("")
    
    link_entries.append("    --- TGEN IXP Links")
    add_bidir_ixp("ftpSrvAddr", server_net_link, "server_net")
    add_bidir_ixp("gorillaSrvAddr", server_net_link, "server_net")
        
    for idx_line, entry in enumerate(link_entries):
        if entry == "":
            L("")
        elif idx_line == len(link_entries) - 1:
            L(f"{entry}")
        else:
            L(entry)
    L("  .")
    L("")
    
    L("  ---------------------------------------------------")
    L("  --- Visibility Map")
    L("  ---------------------------------------------------")
    L("  eq visibilityMap =")
    
    vis_entries = []
    # Map visibility sets to deterministic Maude map structure
    for net_name in sorted(vis_map.keys()):
        addrs = vis_map[net_name]
        if not addrs:
            continue
        net_id = net_id_map[net_name]
        
        if len(addrs) == 1:
            addr_str = addrs[0]
        else:
            _lines = []
            for chunk in chunk_list(addrs, 4):
                _lines.append(" ;; ".join(chunk))
            addr_str = "(\n      " + "\n      ;; ".join(_lines) + "\n    )"
            
        vis_entries.append(f"  ({net_id} |-> {addr_str})")
        
    for idx_line, entry in enumerate(vis_entries):
        if idx_line == len(vis_entries) - 1:
            L(f"{entry}")
        else:
            L(f"{entry} ,")
    L("  .")
    L("")
    
    L("  ---------------------------------------------------")
    L("  --- Actor Declarations & Definitions")
    L("  ---------------------------------------------------")
    L("")
    sky_client = hcs_channel_models.get("skyhook", {}).get("client", "")
    sky_server = hcs_channel_models.get("skyhook", {}).get("server", "")
    mas_client = hcs_channel_models.get("mastodon", {}).get("client", "")
    mas_server = hcs_channel_models.get("mastodon", {}).get("server", "")

    sky_client_ma = ("skyhook-" + sky_client.replace('_', '-') + "-ma") if sky_client else ""
    sky_server_ma = ("skyhook-" + sky_server.replace('_', '-') + "-ma") if sky_server else ""
    mas_client_ma = ("mastodon-" + mas_client.replace('_', '-') + "-ma") if mas_client else ""
    mas_server_ma = ("mastodon-" + mas_server.replace('_', '-') + "-ma") if mas_server else ""        
    hcs_quantity_by_channel = {}
    
    for channel, net_name, qty, profs in hcs_nodes:
        hcs_quantity_by_channel[channel] = qty
    for idx, i in enumerate(hcs_client_ids["webtunnel"]):
        profile = distribute_profiles(hcs_quantity_by_channel["webtunnel"], hcs_profiles_by_channel["webtunnel"])[idx]
        irc_key = f"irc-{profile.replace('_', '-')}"
        L(f"  --- Webtunnel Client {i} (IRC profile: {profile})")
        L(f"  ops wtCl{i}Irc wtCl{i}Um wtCl{i}Iface wtCl{i}SrvIface : -> Actor .")
        L(f"  ops wtCl{i}Client wtCl{i}Proxy : -> Actor .")

        L(f"  eq wtCl{i}Irc       = mkIrcClient-v2(wtCl{i}IrcAddr, wtCl{i}IfaceAddr, \"WtClient{i}\") .")
        L(f"  eq wtCl{i}Um        = mkIrcUMV2Actor(wtCl{i}UmAddr, \"{irc_key}\", wtCl{i}IrcAddr, ircServerAddr, wtCl{i}SrvIfaceAddr) .")
        L(f"  eq wtCl{i}Iface     = mkIrcByteSeqIface(wtCl{i}IfaceAddr, wtCl{i}IrcAddr, wtCl{i}ClientAddr) .")
        L(f"  eq wtCl{i}SrvIface  = mkIrcByteSeqIface(wtCl{i}SrvIfaceAddr, ircServerAddr, wtCl{i}ProxyAddr) .")
        L(f"  eq wtCl{i}Client =")
        L(f"    < wtCl{i}ClientAddr : WtClient |")
        L(f"        thisAddr:        wtCl{i}ClientAddr,")
        L(f"        serverProxyAddr: wtCl{i}ProxyAddr,")
        L(f"        ircServerAddr:   ircServerAddr,")
        L(f"        ircClientAddr:   wtCl{i}IfaceAddr,")
        L(f"        tlsServerName:   \"irc.example.com\",")
        L(f"        upgradePath:     \"secret/path/v1\",")
        L(f"        tunnelState:     Closed,")
        L(f"        pendingMsgs:     emptyQueue > .")
        L(f"  eq wtCl{i}Proxy      = makeWtServerProxy(wtCl{i}ProxyAddr, wtCl{i}SrvIfaceAddr) .")
        L("")        
    
    for idx, i in enumerate(hcs_client_ids["skyhook"]):
        profile = distribute_profiles(hcs_quantity_by_channel["skyhook"], hcs_profiles_by_channel["skyhook"])[idx]
        irc_key = f"irc-{profile.replace('_', '-')}"
        L(f"  --- Skyhook Client {i} (IRC profile: {profile})")
        L(f"  ops skyCl{i}Irc skyCl{i}Um skyCl{i}Iface skyCl{i}SrvIface : -> Actor .")
        L(f"  ops skyCl{i}UmacAct skyCl{i}CmacAct skyCl{i}PuaAct skyCl{i}SdkacAct : -> Actor .")
        L(f"  ops skyCl{i}UmasAct skyCl{i}CmasAct skyCl{i}AhaAct skyCl{i}SdkasAct : -> Actor .")

        
        L(f"  eq skyCl{i}Irc       = mkIrcClient-v2(skyCl{i}IrcAddr, skyCl{i}IfaceAddr, \"SkyClient{i}\") .")
        L(f"  eq skyCl{i}Um        = mkIrcUMV2Actor(skyCl{i}UmAddr, \"{irc_key}\", skyCl{i}IrcAddr, ircServerAddr, skyCl{i}SrvIfaceAddr) .")
        L(f"  eq skyCl{i}Iface     = mkIrcByteSeqIface(skyCl{i}IfaceAddr, skyCl{i}IrcAddr, skyCl{i}CmacAddr) .")
        L(f"  eq skyCl{i}UmacAct   = mkUMactor(skyCl{i}UmacAddr, {sky_client_ma}, skyCl{i}CmacAddr) .")
        L(f"  eq skyCl{i}CmacAct   = mkCMSimpleBi(skyCl{i}CmacAddr, skyCl{i}IfaceAddr, skyCl{i}PuaAddr) .")
        # Object IDs are bucket-scoped decimal generations. The public user's
        # first PUT is generation 1, matching the account holder's initial queue.
        L(f"  eq skyCl{i}PuaAct    = makeSkyhookPU(skyCl{i}PuaAddr, skyCl{i}CmacAddr, skyCl{i}SdkacAddr, \"s_to_c_bucket_{i}\", \"c_to_s_bucket_{i}\", \"0\", \"1\") .")
        L(f"  eq skyCl{i}SdkacAct  = makeS3Client(skyCl{i}SdkacAddr, s3SrvAddr) .")
        L(f"  eq skyCl{i}SrvIface  = mkIrcByteSeqIface(skyCl{i}SrvIfaceAddr, ircServerAddr, skyCl{i}CmasAddr) .")
        L(f"  eq skyCl{i}UmasAct   = mkUMactor(skyCl{i}UmasAddr, {sky_server_ma}, skyCl{i}CmasAddr) .")
        L(f"  eq skyCl{i}CmasAct   = mkCMSimpleBi(skyCl{i}CmasAddr, skyCl{i}SrvIfaceAddr, skyCl{i}AhaAddr) .")
        L(f"  eq skyCl{i}AhaAct    = mkSkyhookAH(skyCl{i}AhaAddr, skyCl{i}CmasAddr, skyCl{i}SdkasAddr, \"c_to_s_bucket_{i}\", \"s_to_c_bucket_{i}\", \"0\", \"0\", \"0\", 100) .")
        L(f"  eq skyCl{i}SdkasAct  = makeS3Client(skyCl{i}SdkasAddr, s3SrvAddr) .")
        L("")        
    
    for idx, i in enumerate(hcs_client_ids["obfs4"]):
        profile = distribute_profiles(hcs_quantity_by_channel["obfs4"], hcs_profiles_by_channel["obfs4"])[idx]
        irc_key = f"irc-{profile.replace('_', '-')}"
        L(f"  --- OBFS4 Client {i} (IRC profile: {profile})")
        L(f"  ops obfsCl{i}Irc obfsCl{i}Um obfsCl{i}Iface obfsCl{i}SrvIface : -> Actor .")
        L(f"  ops obfsCl{i}Cl obfsCl{i}Srv : -> Actor .")

        
        L(f"  eq obfsCl{i}Irc      = mkIrcClient-v2(obfsCl{i}IrcAddr, obfsCl{i}IfaceAddr, \"ObfsClient{i}\") .")
        L(f"  eq obfsCl{i}Um       = mkIrcUMV2Actor(obfsCl{i}UmAddr, \"{irc_key}\", obfsCl{i}IrcAddr, ircServerAddr, obfsCl{i}SrvIfaceAddr) .")
        L(f"  eq obfsCl{i}Iface    = mkIrcByteSeqIface(obfsCl{i}IfaceAddr, obfsCl{i}IrcAddr, obfsCl{i}ClientAddr) .")
        L(f"  eq obfsCl{i}Cl       = makeObfs4Node(obfsCl{i}ClientAddr, obfsCl{i}IfaceAddr, obfsCl{i}ServerAddr) .")
        L(f"  eq obfsCl{i}SrvIface = mkIrcByteSeqIface(obfsCl{i}SrvIfaceAddr, ircServerAddr, obfsCl{i}ServerAddr) .")
        L(f"  eq obfsCl{i}Srv      = makeObfs4Node(obfsCl{i}ServerAddr, obfsCl{i}SrvIfaceAddr, obfsCl{i}ClientAddr) .")
        L("")
            
    for idx, i in enumerate(hcs_client_ids["iodine"]):
        profile = distribute_profiles(hcs_quantity_by_channel["iodine"], hcs_profiles_by_channel["iodine"])[idx]
        irc_key = f"irc-{profile.replace('_', '-')}"
        t_id = idx+1
        L(f"  --- Iodine Client {i} (IRC profile: {profile})")
        L(f"  ops iodCl{i}Irc iodCl{i}Um iodCl{i}Iface iodCl{i}SrvIface : -> Actor .")
        L(f"  ops iodCl{i}SendApp iodCl{i}RcvApp iodCl{i}Cl iodCl{i}Srv : -> Actor .")
        L(f"  ops iodCl{i}SrvNetCl iodCl{i}SrvNetSrv : -> Actor .")
        
        L(f"  eq iodCl{i}Irc       = mkIrcClient-v2(iodCl{i}IrcAddr, iodCl{i}IfaceAddr, \"IodClient{i}\") .")
        L(f"  eq iodCl{i}Um        = mkIrcUMV2Actor(iodCl{i}UmAddr, \"{irc_key}\", iodCl{i}IrcAddr, ircServerAddr, iodCl{i}SrvIfaceAddr) .")
        L(f"  eq iodCl{i}Iface     = mkIrcByteSeqIface(iodCl{i}IfaceAddr, iodCl{i}IrcAddr, iodCl{i}SendAppAddr) .")
        L(f"  eq iodCl{i}SrvIface  = mkIrcByteSeqIface(iodCl{i}SrvIfaceAddr, ircServerAddr, iodCl{i}RcvAppAddr) .")
        L(f"  eq iodCl{i}SendApp   = mkSendAppWithStream(iodCl{i}SendAppAddr, iodCl{i}RcvAppAddr, iodCl{i}IfaceAddr, iodCl{i}ClientAddr, {2*i}) .")
        L(f"  eq iodCl{i}RcvApp    = mkRcvAppWithStream(iodCl{i}RcvAppAddr, iodCl{i}SendAppAddr, iodCl{i}SrvIfaceAddr, iodCl{i}ServerAddr, {2*i+1}) .")
        L(f"  eq iodCl{i}Cl        = makeWClient(iodCl{i}ClientAddr, corpIodDnsAddr, 't{t_id} . 'pwnd . 'com . root, a, 0.0) .")
        L(f"  eq iodCl{i}Srv       = makeWNameServer(iodCl{i}ServerAddr, 0.0, zonePwndDef) .")
        L(f"  eq iodCl{i}SrvNetSrv = mkPubDnsNetS(iodCl{i}SrvNetSrvAddr,")
        L(f"                                    iodCl{i}ServerAddr,")
        L(f"                                    IXP-DEFAULT-ADDR) .")
        L(f"  **** pubDns as client side ")
        L(f"  eq iodCl{i}SrvNetCl = mkFwdDnsNetC(iodCl{i}SrvNetClAddr,")
        L(f"                                   iodCl{i}SrvNetSrvAddr,")
        L(f"                                   iodCl{i}ServerAddr, ")
        L(f"                                   publicDnsAddr,")
        L(f"                                   IXP-DEFAULT-ADDR) .")
        L("")
        
    for idx, i in enumerate(hcs_client_ids["mastodon"]):
        profile = distribute_profiles(hcs_quantity_by_channel["mastodon"], hcs_profiles_by_channel["mastodon"])[idx]
        irc_key = f"irc-{profile.replace('_', '-')}"
        L(f"  --- Mastodon HCS Client {i} (IRC profile: {profile})")
        L(f"  ops masCl{i}Irc masCl{i}Um masCl{i}Iface masCl{i}SrvIface : -> Actor .")
        L(f"  ops masCl{i}UmacAct masCl{i}CmacAct masCl{i}McacAct masCl{i}EdacAct : -> Actor .")
        L(f"  ops masCl{i}UmasAct masCl{i}CmasAct masCl{i}McasAct masCl{i}EdasAct : -> Actor .")

        
        L(f"  eq masCl{i}Irc       = mkIrcClient-v2(masCl{i}IrcAddr, masCl{i}IfaceAddr, \"MasClient{i}\") .")
        L(f"  eq masCl{i}Um        = mkIrcUMV2Actor(masCl{i}UmAddr, \"{irc_key}\", masCl{i}IrcAddr, ircServerAddr, masCl{i}SrvIfaceAddr) .")
        L(f"  eq masCl{i}Iface     = mkIrcByteSeqIface(masCl{i}IfaceAddr, masCl{i}IrcAddr, masCl{i}CmacAddr) .")
        L(f"  eq masCl{i}UmacAct   = mkUMactor(masCl{i}UmacAddr, {mas_client_ma}, masCl{i}CmacAddr) .")
        L(f"  eq masCl{i}CmacAct   = mkCMSndRcvActor(masCl{i}CmacAddr, masCl{i}EdacAddr, masCl{i}McacAddr, masCl{i}IfaceAddr, \"client{i}\", \"server{i}\") .")
        L(f"  eq masCl{i}McacAct   = makeMastodonClient(masCl{i}McacAddr, masSrvAddr, masCl{i}CmacAddr) .")
        L(f"  eq masCl{i}EdacAct   = makeDestiniActor(masCl{i}EdacAddr, ed-images) .")
        L(f"  eq masCl{i}SrvIface  = mkIrcByteSeqIface(masCl{i}SrvIfaceAddr, ircServerAddr, masCl{i}CmasAddr) .")
        L(f"  eq masCl{i}UmasAct   = mkUMactor(masCl{i}UmasAddr, {mas_server_ma}, masCl{i}CmasAddr) .")
        L(f"  eq masCl{i}CmasAct   = mkCMSndRcvActor(masCl{i}CmasAddr, masCl{i}EdasAddr, masCl{i}McasAddr, masCl{i}SrvIfaceAddr, \"server{i}\", \"client{i}\") .")
        L(f"  eq masCl{i}McasAct   = makeMastodonClient(masCl{i}McasAddr, masSrvAddr, masCl{i}CmasAddr) .")
        L(f"  eq masCl{i}EdasAct   = makeDestiniActor(masCl{i}EdasAddr, ed-images) .")
        L("")
    
    L("  --- Base Infrastructure")
    L("  ops ircServer s3SrvAct advActor masSrvAct transportActor : -> Actor .")
    L("  eq ircServer      = mkIrcServer(ircServerAddr) .")
    L("  eq s3SrvAct       = ")
    L("    < s3SrvAddr : AwsS3HttpServer |")
    L("        thisAddr: s3SrvAddr,")
    if any(inst.tgen_type == "minTgen" for inst in tgen_instances):
        L("        s3DataMap: (")
        L("          (\"/tgen/list-1\" -> restToByteSeq(\"obj1.zip;obj2.zip;data/\")) ;")
        L("          (\"/tgen/stat-1\" -> restToByteSeq(\"obj1.zip:1024:2025-01-01\")) ;")
        L("          (\"/tgen/cd-1\" -> restToByteSeq(\"subdir1/;subdir2/\")) ;")
        L("          (\"/tgen/retr-1\" -> restToByteSeq(\"mock_file_content_bytes\"))")
        L("        )")
    else:
        L("        s3DataMap: emptyS3DataMap")
    L("    >")
    L("  .")
    L("  eq masSrvAct      = makeMastodonServer(masSrvAddr) .")
    L("  --- The global actor takes endpoints from each message/connection handle.")
    L("  eq transportActor = makeTransportActor(transportAddr,")
    L("      nullAddr, nullAddr, servDnsAddr, 'mastodon . 'pwnd . 'com . root) .")
    adv_use_tcp = "false" if perf and not force_observer else "true"
    L(f"  eq advActor       = mkAdversaryCp3(advAddr, {adv_use_tcp}) .")
    L("")
    
    L("  --- DNS Infrastructure")
    L("  ops corpMasDns corpRtDns corpIodDns corpObfsDns corpSkyDns servDns : -> Actor .")
    L("  ops publicResolver rootDns tldDns authDns : -> Actor .")
    L("  ops corpMasNetCl corpRtNetCl corpIodNetCl corpObfsNetCl corpSkyNetCl servNetCl : -> Actor .")
    L("  ops publicResolverNetSrv : -> Actor .")
    L("")
    L("  eq corpMasDns   = mkNameServer(corpMasDnsAddr, (zoneMasCom), corpMasNetClAddr) .")
    L("  eq corpRtDns    = mkNameServer(corpRtDnsAddr, (zoneRtCom), corpRtNetClAddr) .")
    L("  eq corpIodDns   = mkNameServer(corpIodDnsAddr, (zoneIodCom), corpIodNetClAddr) .")
    L("  eq corpObfsDns  = mkNameServer(corpObfsDnsAddr, (zoneObfsCom), corpObfsNetClAddr) .")
    L("  eq corpSkyDns   = mkNameServer(corpSkyDnsAddr, (zoneSkyCom), corpSkyNetClAddr) .")
    L("  eq servDns      = mkNameServer(servDnsAddr, (zoneServCom), servNetClAddr) .")
    L("  eq publicResolver = mkResolver(publicDnsAddr, resolverCache, sb) .")
    L("  eq rootDns       = mkNameServer(rootDnsAddr, (zone), nullAddr) .")
    L("  eq tldDns        = mkNameServer(tldDnsAddr, (zoneCom), nullAddr) .")
    L("  eq authDns       = mkNameServer(authDnsAddr, (zoneInternetCom zonePwndCom), nullAddr) .")
    L("")
    L("  eq corpMasNetCl = mkFwdDnsNetC(corpMasNetClAddr,")
    L("                                 publicResolverNetSrvAddr,")
    L("                                 publicDnsAddr,")
    L("                                 corpMasDnsAddr,")
    L("                                 IXP-DEFAULT-ADDR)")
    L("  .")
    L("  eq corpRtNetCl  = mkFwdDnsNetC(corpRtNetClAddr,")
    L("                                 publicResolverNetSrvAddr,")
    L("                                 publicDnsAddr,")
    L("                                 corpRtDnsAddr,")
    L("                                 IXP-DEFAULT-ADDR)")
    L("  .")
    L("  eq corpIodNetCl = mkFwdDnsNetC(corpIodNetClAddr,")
    L("                                 publicResolverNetSrvAddr,")
    L("                                 publicDnsAddr,")
    L("                                 corpIodDnsAddr,")
    L("                                 IXP-DEFAULT-ADDR)")
    L("  .")
    L("  eq corpObfsNetCl  = mkFwdDnsNetC(corpObfsNetClAddr,")
    L("                                   publicResolverNetSrvAddr,")
    L("                                   publicDnsAddr,")
    L("                                   corpObfsDnsAddr,")
    L("                                   IXP-DEFAULT-ADDR)")
    L("  .")
    L("  eq corpSkyNetCl = mkFwdDnsNetC(corpSkyNetClAddr,")
    L("                                 publicResolverNetSrvAddr,")
    L("                                 publicDnsAddr, ")
    L("                                 corpSkyDnsAddr,")
    L("                                 IXP-DEFAULT-ADDR)")
    L("  .")
    L("  eq servNetCl  = mkFwdDnsNetC(servNetClAddr,")
    L("                               publicResolverNetSrvAddr,")
    L("                               publicDnsAddr,")
    L("                               servDnsAddr,")
    L("                               IXP-DEFAULT-ADDR)")
    L("  .")
    L("  eq publicResolverNetSrv = mkPubDnsNetS(publicResolverNetSrvAddr,")
    L("                                         publicDnsAddr,")
    L("                                         IXP-DEFAULT-ADDR)")
    L("  .")
    L("")
    
    L("  ---------------------------------------------------")
    emit_tgen_definitions(L, tgen_instances, resolver_for_network)

    L("  --- Initial State Configuration")
    L("  ---------------------------------------------------")
    L("  op initState : Nat -> Config .")
    L("  eq initState(j) =")    
    L("")
    if not perf:
        L("    --- Baseline actor")
        L("    baseLineAct")
        L("")
    L("    --- Core Infrastructure")
    L("    ircServer s3SrvAct masSrvAct")
    L("    mkIrcMonitor(ircMonitorAddr)")
    L("    servDns servNetCl")
    L("    advActor")
    if transport_mode == "tcp":
        L("    transportActor")
    L("")
    for i in hcs_client_ids["webtunnel"]:
        L(f"    --- Webtunnel Client {i}")
        L(f"    wtCl{i}Irc wtCl{i}Um wtCl{i}Iface wtCl{i}SrvIface wtCl{i}Client wtCl{i}Proxy")

    L("    corpRtDns corpRtNetCl")
    L("")
    for i in hcs_client_ids["skyhook"]:
        L(f"    --- Skyhook Client {i}")
        L(f"    skyCl{i}Irc skyCl{i}Um skyCl{i}Iface skyCl{i}UmacAct skyCl{i}CmacAct skyCl{i}PuaAct skyCl{i}SdkacAct")
        L(f"    skyCl{i}SrvIface skyCl{i}UmasAct skyCl{i}CmasAct skyCl{i}AhaAct skyCl{i}SdkasAct")

    L("    corpSkyDns corpSkyNetCl")
    L("")
    for i in hcs_client_ids["obfs4"]:
        L(f"    --- OBFS4 Client {i}")
        L(f"    obfsCl{i}Irc obfsCl{i}Um obfsCl{i}Iface obfsCl{i}SrvIface obfsCl{i}Cl obfsCl{i}Srv")

    L("    corpObfsDns corpObfsNetCl")
    L("")
    for i in hcs_client_ids["iodine"]:
        L(f"    --- Iodine Client {i}")
        L(f"    iodCl{i}Irc iodCl{i}Um iodCl{i}Iface iodCl{i}SrvIface")
        L(f"    iodCl{i}SendApp iodCl{i}RcvApp iodCl{i}Cl iodCl{i}Srv")
        L(f"    iodCl{i}SrvNetSrv iodCl{i}SrvNetCl")
    L("    corpIodDns corpIodNetCl")
    L("")
    for i in hcs_client_ids["mastodon"]:
        L(f"    --- Mastodon HCS Client {i}")
        L(f"    masCl{i}Irc masCl{i}Um masCl{i}Iface masCl{i}SrvIface")
        L(f"    masCl{i}UmacAct masCl{i}CmacAct masCl{i}McacAct masCl{i}EdacAct")
        L(f"    masCl{i}UmasAct masCl{i}CmasAct masCl{i}McasAct masCl{i}EdasAct")

    L("    corpMasDns corpMasNetCl")
    L("")
    L("    --- DNS Infrastructure")
    L("    publicResolver publicResolverNetSrv")
    L("    rootDns tldDns authDns")
    L("")
    L("")
    emit_tgen_initial_actors(L, tgen_instances)
    L("")
    L("    --- Startup Timers")
    L("")
    timer_j = 1
    start_noise = 0.009
    for i in hcs_client_ids["skyhook"]:
        L(f"    [hcsDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to skyCl{i}AhaAddr from skyCl{i}AhaAddr : SkyhookStartCmd), 0]"); timer_j += 1
        L(f"    [hcsDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to skyCl{i}UmacAddr from skyCl{i}UmacAddr : actionR(\"ok\")), 0]"); timer_j += 1
        L(f"    [hcsDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to skyCl{i}UmasAddr from skyCl{i}UmasAddr : actionR(\"ok\")), 0]"); timer_j += 1
        L(f"    [hcsDelay + 10.0 + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to skyCl{i}UmAddr from skyCl{i}UmAddr : burstDelayTO), 0]"); timer_j += 1
    for i in hcs_client_ids["webtunnel"]:
        L(f"    [hcsDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to wtCl{i}ClientAddr from wtCl{i}ClientAddr : WtStartCmd), 0]"); timer_j += 1
        L(f"    [hcsDelay + 10.0 + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to wtCl{i}UmAddr from wtCl{i}UmAddr : burstDelayTO), 0]"); timer_j += 1
    for i in hcs_client_ids["iodine"]:
        L(f"    [hcsDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to iodCl{i}SendAppAddr : start), 0]"); timer_j += 1
        L(f"    [hcsDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to iodCl{i}RcvAppAddr : start), 0]"); timer_j += 1 
        L(f"    [hcsDelay + 10.0 + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to iodCl{i}UmAddr from iodCl{i}UmAddr : burstDelayTO), 0]"); timer_j += 1   
    for i in hcs_client_ids["mastodon"]:    
        L(f"    [hcsDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to masCl{i}UmacAddr from masCl{i}UmacAddr : actionR(\"ok\")), 0]"); timer_j += 1
        L(f"    [hcsDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to masCl{i}UmasAddr from masCl{i}UmasAddr : actionR(\"ok\")), 0]"); timer_j += 1
        L(f"    [hcsDelay + 10.0 + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to masCl{i}UmAddr from masCl{i}UmAddr : burstDelayTO), 0]"); timer_j += 1    
    for i in hcs_client_ids["obfs4"]:
        L(f"    [hcsDelay + 10.0 + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to obfsCl{i}UmAddr from obfsCl{i}UmAddr : burstDelayTO), 0]"); timer_j += 1
    L("")
    
    if not notgens:
        L("    --- TGEN User Model Burst Delay Timers (staggered)")
        timer_j = emit_tgen_start_timers(L, tgen_instances, timer_j, start_noise)
        L("")    
    if not perf:
        L(f"[ksWindowDelay + genRandomX(j + {timer_j}, 0.0, {start_noise}), (to baseLineAddr from baseLineAddr : initKs),0]")
        timer_j += 1
    L(f"    rCtr(j + {timer_j})")
    L("  .")
    L("")    
    L("  ---------------------------------------------------")
    L("  --- Run Limits and Initial Configuration")
    L("  ---------------------------------------------------")
    L("  ***** suppressing irc server dropping clients")
    L("  eq IRC-STALE-DURATION-S = 140000. [owise] .")
    L("  eq IRC-PING-INTV-S = 1200000. [owise]  .")
    L("  ")
    L("  op slimit : -> Float .")
    L(f"  eq slimit = {duration:.1f} [owise] .")
    L("")
    L("  op initConfig : -> Config .")
    L("  rl[init]: initConfig => run({0.0 | nil} initState(counter), slimit) .")
    L("")
    L("  op allClientsAddr : -> AddrList .")
    all_clients = get_client_lst(hcs_client_ids)
            
    L(f"  eq allClientsAddr = {' ; '.join(all_clients) if all_clients else 'nil'} .")
    L("endm")
    L("eof")
    L("--- set print attribute on .")
    L("--- rew initConfig .")
    L("--- q")
    
    return "\n".join(lines)

# Generate baseline or run scenario file
def gen_baselineEq(scenario_name):
    lines = []
    L = lines.append
    """
    set show advisories off .

    *** sload smc-baseline-shared
    sload {lib}/smc/smc-baseline-shared

    mod {scenario-name}-BL-EQ is
    inc SMC-BASELINE-SHARED .

    eq BL = nilBaseLine .

    endm
    eof
    """
    L(f"sload {GLOBALS.LIB_DIR}/smc/smc-baseline-shared")
    L("")
    L("")
    
    mod_name = scenario_name.upper().replace("_", "-")
    suffix = "BASELINE-EQ"
    L(f"mod {mod_name}-{suffix} is")    
    L("  inc SMC-BASELINE-SHARED .")
    L("  ")
    L("  ---- insert baseline output here ---")
    L("  eq BL = nilBaseLine .")
    L("")
    L("endm")
    L("eof")    
    
    return "\n".join(lines)

# Generate baseline or run scenario file
def gen_baselineOrRun_file(scenario_name, isBaseline=True, perf=False, baseline_time=None, run_time=None, feature=None, vpt=None):
    lines = []
    L = lines.append

    assert (baseline_time is not None) or (run_time is not None)

    prefix = ""
    if feature and vpt:
        # we are generating baselines insside <out_dir>/baselines so we need ../ in paths
        prefix = "../"
    
    L(f"sload {prefix}{scenario_name}")
    L(f"sload {prefix}{GLOBALS.LIB_DIR}/smc/smc_cp3-refactored")
    if not perf:
        L("")
        if not isBaseline:
            eqSuffix = ""
            L(f"sload {scenario_name}-baseline-eq{eqSuffix}")    
        L("")
    
    mod_name = scenario_name.upper().replace("_", "-")    
    # suffix = "-BASELINE" if isBaseline else ""
    suffix = "" # Changing the module name breaks SMC
    if feature and vpt:
        mod_name_ext = f"{smc_mod_name}{suffix}-{feature.upper()}-{vpt.upper().replace("[","").replace("]","")}".replace("_", "-")
        L(f"mod {mod_name_ext} is")
    else:
        L(f"mod {smc_mod_name}{suffix} is")
    L(f"  inc {mod_name} .  ") 
    L("  inc SMC_CP3 . ")
    if not perf:
        if not isBaseline:
            L(f"  inc {mod_name}-BASELINE-EQ . ")
        L("  ")

    if baseline_time is not None and isBaseline:
        L(f"eq slimit = {baseline_time:.1f} .")
    else:
        L(f"eq slimit = {run_time:.1f} .")
    
    if not perf:
        if feature and vpt:
            L("")
            L(f"  eq Vpts = {vpt} .")
            L(f"  eq ObsFs = {feature} .")
            
        L("")
        if not isBaseline:
            L(f"  eq ksWindowDelay = hcsDelay .") # only in the run file
        if isBaseline:
            L("  eq hcsDelay = slimit + slimit .  --- prevent hcs from starting")
            L("")
            L(" eq finalize(c:Config) = addK2Blist(c:Config,false) .")
        else:
            L(" eq finalize(c:Config) = mvKs2Adv(c:Config,true) .")
        L("")
    L("endm")
    L("")
    # if isBaseline:
    #     L("rew run({0.0 | nil} initState(counter) [tgenDelay, (to baseLineAddr from baseLineAddr : initBase),0], slimit) .")
    #     L("q")
    # else:
        # L("---rew initConfig .")
        # L("---q")
    
    return "\n".join(lines)

def prepare_user_models(yaml_file, out_dir, tgen_instances):
    """Copy scenario profiles and convert their JSON alongside the experiment."""
    from . import convert_markov_json_to_maude_v1 as v1
    from . import convert_markov_json_to_maude_v2 as v2

    scenario_dir = Path(yaml_file).parent
    folders = [("skyhook_action_models", "skyhook", v1),
               ("mastodon_action_models", "mastodon", v1),
               ("irc_user_models", "irc", v2)]
    tgen_protocols = {"masTgen": ("mastodon", "mastodon-tgen", v1),
                      "dnsTgen": ("dns", "dns-tgen", v1),
                      "ftpTgen": ("ftp", "ftp", v2),
                      "minTgen": ("minio", "minio", v2),
                      "gorTgen": ("gorilla", "gorilla", v2),
                      "ircTgen": ("irc", "irc", v2)}
    for kind in sorted({inst.tgen_type for inst in tgen_instances}):
        folder, protocol, converter = tgen_protocols[kind]
        folders.append(("tgen_user_models/" + folder, protocol, converter))
    for folder, protocol, converter in folders:
        source, target = scenario_dir / folder, Path(out_dir) / folder
        if not source.is_dir():
            continue
        if source.resolve() != target.resolve():
            shutil.copytree(source, target, dirs_exist_ok=True)
        converter.process_directories(argparse.Namespace(protocol=protocol), str(target), str(target))


def generate(args: argparse.Namespace):

    yaml_file = os.path.abspath(args.yaml_file)
    baseline_time = args.baselineTime
    run_time = args.runTime
    hcs_delay: int = args.hcsDelay
    tgen_delay: int = args.tgenDelay    
    out_dir = os.path.abspath(args.outDir) if args.outDir is not None else os.path.dirname(yaml_file)
    scenario_name = args.scenarioName if args.scenarioName is not None else os.path.splitext(os.path.basename(yaml_file))[0]

    if hcs_delay is not None and tgen_delay is not None:
        assert tgen_delay <= hcs_delay

    if args.parallelizeBaseline:
        assert args.baselineTime is not None

    if args.feats is not None:
        selected_feats = filter_feats(args.feats)
    else:
        selected_feats = FEATURES

    logger.info("arg.vpts: %s", args.vpts)
    if args.vpts is not None:
        selected_vpts = filter_vpts(args.vpts)
    else:
        selected_vpts = VANTAGE_POINTS
    logger.info("selected_vpts: %s", selected_vpts)

    delay = max(hcs_delay, tgen_delay)

    logger.info("Execution Arguments:")
    for arg, value in vars(args).items():
        logger.info("  %s: %s", arg, value)
    logger.info("  effective out_dir: %s", out_dir)
    logger.info("  effective scenario_name: %s", scenario_name)
    logger.info("-" * 40)
    
    logger.info("Parsing scenario YAML from: %s", yaml_file)
    yaml_duration, analysis_window_size, networks, net_id_map, net_short, loss_profiles, hcs_nodes, hcs_profiles_by_channel, tgen_defs, hcs_channel_models = parse_scenario_yaml(yaml_file)


    logger.info("hcs_nodes: %s", hcs_nodes)
    logger.info("Net id mapping: %s", json.dumps(net_id_map, indent=4))

    valid_vpts = list(filter(lambda x: x in net_id_map, selected_vpts))
    logger.info("valid_vpts: %s", valid_vpts)
    maude_vpts = list(map(lambda vpt: net_id_map[vpt], valid_vpts))
    logger.info("maude_vpts: %s", maude_vpts)
    
    if run_time is None:
        logger.info("Loaded duration: %ss", yaml_duration)
        run_time = yaml_duration
    else:
        logger.info("loaded duration from yaml was %ss, overridden with provided run_time %ss", yaml_duration, run_time)

    tgen_instances = [] if args.notgens else generate_all_tgen_instances(tgen_defs, net_id_map, net_short)
    selected_types = getattr(args, "tgen_types", None)
    if selected_types:
        kinds = {"mastodon": "masTgen", "ftp": "ftpTgen", "dns": "dnsTgen",
                 "minio": "minTgen", "gorilla": "gorTgen", "irc": "ircTgen"}
        selected = {kinds[kind] for kind in selected_types}
        tgen_instances = [inst for inst in tgen_instances if inst.tgen_type in selected]
    _validate(tgen_instances)
    
    logger.info("Parsed %s networks", len(networks))
    logger.info("Parsed %s loss profiles", len(loss_profiles))
    logger.info("Generated %s TGEN instances", len(tgen_instances))
    for ttype in ["masTgen", "ftpTgen", "dnsTgen", "minTgen", "gorTgen", "ircTgen"]:
        count = sum(1 for i in tgen_instances if i.tgen_type == ttype)
        logger.info("  %s: %s", ttype, count)
    
    os.makedirs(out_dir, exist_ok=True)
    prepare_user_models(yaml_file, out_dir, tgen_instances)

    # Generate addresses file
    addr_content, hcs_client_ids = gen_addresses_file(hcs_nodes, tgen_instances, net_id_map, scenario_name, args.notgens)
    addr_path = os.path.join(out_dir, f"{scenario_name}_addresses.maude")
    with open(addr_path, "w") as f:
        f.write(addr_content)
    logger.info("\nWrote %s (%s) lines)", addr_path, len(addr_content.splitlines()))

    # Generate main file
    main_content = gen_main_file(
        tgen_instances, networks, loss_profiles, hcs_profiles_by_channel, run_time+delay,
        hcs_channel_models, hcs_client_ids, hcs_nodes, scenario_name, net_id_map,
        hcs_delay, tgen_delay, maude_vpts, features=selected_feats,
        perf=args.perf, force_observer=args.force_observer, notgens=args.notgens,
        transport_mode=getattr(args, "transport", "tcp"),
    )
    main_path = os.path.join(out_dir, f"{scenario_name}.maude")
    with open(main_path, "w") as f:
        f.write(main_content)
    logger.info("Wrote %s %s lines", main_path, len(main_content.splitlines()))

    manifest = {
        "scenario": scenario_name,
        "yaml_file": yaml_file,
        "transport": getattr(args, "transport", "tcp"),
        "transport_actors": 1 if getattr(args, "transport", "tcp") == "tcp" else 0,
        "lossless_links": True,
        "hcs_clients": hcs_client_ids,
        "tgens": [vars(inst) for inst in tgen_instances],
        "dns_resolvers": dict(tcp_endpoint_policy(hcs_nodes, tgen_instances)),
        "dns_name": "mastodon.pwnd.com",
        "notes": ["Monitor-only TGEN entries are omitted.",
                  "The shared DNS name models lookup completion; TCP retains the message destination.",
                  "TGEN protocol compatibility is not guaranteed by generation."],
    }
    Path(out_dir, f"{scenario_name}-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    all_clients = get_client_lst(hcs_client_ids)

    logger.info("Features: %s", selected_feats)
    logger.warning("Vantage points: %s", maude_vpts)
    logger.info("Clients: %s", all_clients)

    # Write queries to chosen quatex file path
    if args.quatex:
        quatex_filename = f"{scenario_name}.quatex"    
        quatex_path = os.path.join(out_dir, quatex_filename)
        max_win = math.floor(run_time/analysis_window_size)
        assert max_win > 0, "max_win is zero, so no quatex queries would be generated! Are you sure you set the experiment duration high enough?"
        write_all_queries_to_file(Config(selected_feats, maude_vpts, all_clients, window_size=int(analysis_window_size), max_win=int(max_win), delay=int(delay), perf_only=args.perf, conf_only=args.confidentiality), Path(quatex_path))
        logger.info("Wrote quatex queries to %s: max_win: %s, delay: %s", quatex_path, max_win, delay)

    # Generate baseline file    
    if baseline_time is not None:
        baseline_filename_no_ext = f"{scenario_name}-baseline-{baseline_time}"

        if args.parallelizeBaseline:
            baselines_dir = os.path.join(out_dir, "baselines")
            os.makedirs(baselines_dir, exist_ok=True)
            
            for feature in selected_feats:
                for vpt in maude_vpts:
                    p_content = gen_baselineOrRun_file(
                        scenario_name, 
                        isBaseline=True, 
                        perf=args.perf,
                        baseline_time=baseline_time,
                        feature=feature,
                        vpt=vpt,
                    )
                    p_filename = f"{baseline_filename_no_ext}-{feature}-{vpt.replace("[","").replace("]","")}.maude"
                    p_path = os.path.join(baselines_dir, p_filename)
                    with open(p_path, "w") as f:
                        f.write(p_content)
            logger.info("Wrote %s parallel baseline files to %s", len(selected_feats) * len(maude_vpts), baselines_dir)

        else:
            baseline_content = gen_baselineOrRun_file(scenario_name, isBaseline=True, perf=args.perf, baseline_time=baseline_time)
            baseline_filename = f"{baseline_filename_no_ext}.maude"
            baseline_path = os.path.join(out_dir, baseline_filename)
            with open(baseline_path, "w") as f:
                f.write(baseline_content) 
            logger.info("Wrote %s (%s) lines", baseline_path, len(baseline_content.splitlines()))

            # Generate the baseline eq
            baselin_eq_content = gen_baselineEq(scenario_name)
            eq_filename = f"{scenario_name}-baseline-eq-tmp.maude"
            eq_path = os.path.join(out_dir, eq_filename)
            with open(eq_path, "w") as f:
                f.write(baselin_eq_content)    
            logger.info("Wrote %s (%s) lines", eq_path, len(baselin_eq_content.splitlines()))
    
    # Generate run file
    run_content = gen_baselineOrRun_file(scenario_name, isBaseline=False, perf=args.perf, run_time=run_time+delay)

    run_filename = f"{scenario_name}-run.maude"    
    run_path = os.path.join(out_dir, run_filename)
    with open(run_path, "w") as f:
        f.write(run_content)    
    logger.info("Wrote %s (%s) lines", run_path, len(run_content.splitlines()))


def main():
    """CLI: python -m maude_hcs.generate_cp3 --yaml-file PATH --out-dir DIR."""
    parser = argparse.ArgumentParser(description="Generate scenario HCSs and TGENs with one TransportActor and lossless links at configured delays.")
    parser.add_argument("--yaml-file", required=True)
    parser.add_argument("--out-dir", dest="outDir", required=True)
    parser.add_argument("--scenario-name", dest="scenarioName")
    parser.add_argument("--run-time", dest="runTime", type=float)
    parser.add_argument("--baseline-time", dest="baselineTime", type=float)
    parser.add_argument("--hcs-delay", dest="hcsDelay", type=float, default=10.0)
    parser.add_argument("--tgen-delay", dest="tgenDelay", type=float, default=1.0)
    parser.add_argument("--parallelize-baseline", dest="parallelizeBaseline", action="store_true")
    parser.add_argument("--feats", nargs="*")
    parser.add_argument("--vpts", nargs="*")
    parser.add_argument("--quatex", action="store_true")
    parser.add_argument("--confidentiality", action="store_true")
    parser.add_argument("--transport", choices=("tcp", "direct"), default="tcp")
    parser.add_argument("--notgens", action="store_true", help="Omit TGEN actors for an HCS-only comparison.")
    parser.add_argument("--tgen-types", nargs="+", choices=("mastodon", "ftp", "dns", "minio", "gorilla", "irc"), help="Include only these TGEN types (all types by default).")
    parser.set_defaults(perf=True, force_observer=True)
    generate(parser.parse_args())


if __name__ == "__main__":
    main()
