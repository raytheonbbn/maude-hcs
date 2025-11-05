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
from pathlib import Path
import yaml
import shlex
import os

from maude_hcs.parsers.graph import Topology

logger = logging.getLogger(__name__)

class ShadowConfig:
    """
    A Python object representing the parsed Shadow YAML configuration.
    This class acts as the root container for the entire configuration.
    """
    def __init__(self, network:Topology = None, hosts=None, general=None):
        # Stores the network topology configuration
        self.network = network
        # Stores a dictionary of host configurations, keyed by host name
        self.hosts = hosts if hosts is not None else {}
        # Stores general simulation settings
        self.general = general

    def __repr__(self):
        return f"ShadowConfig(general={self.general}, network={self.network}, hosts={self.hosts})"

class GeneralConfig:
    """
    Represents general simulation settings.
    """
    def __init__(self, stop_time=None, data_directory=None, template_directory=None):
        self.stop_time = stop_time
        self.data_directory = data_directory
        self.template_directory = template_directory

    def __repr__(self):
        return f"GeneralConfig(stop_time={self.stop_time}, data_directory='{self.data_directory}', template_directory='{self.template_directory}')"


# class NetworkConfig:
#     """
#     Represents the network configuration, typically defining the topology.
#     """
#     def __init__(self, graph_type=None, graph_path=None):
#         # Type of the network graph (e.g., 'gml', 'graphml')
#         self.graph_type = graph_type
#         # Path to the network graph file
#         self.graph_path = graph_path

#     def __repr__(self):
#         return f"NetworkConfig(graph_type='{self.graph_type}', graph_path='{self.graph_path}')"

class HostConfig:
    """
    Represents the configuration for a single host (node) in the simulation.
    """
    def __init__(self, name, network_node_id, ip_addr=None, processes=None,
                 bandwidth_up=None, bandwidth_down=None, latency=None,
                 cpu_frequency=None, cpu_threshold=None, cpu_precision=None,
                 log_level=None, pcap_directory=None, heart_beat_log_level=None,
                 heart_beat_interval=None):
        self.name = name # The unique name of the host
        self.network_node_id = network_node_id # ID linking to a node in the network graph
        self.ip_addr = ip_addr # Static IP address for the host
        self.processes = processes if processes is not None else [] # List of processes to run on this host
        self.bandwidth_up = bandwidth_up # Uplink bandwidth
        self.bandwidth_down = bandwidth_down # Downlink bandwidth
        self.latency = latency # Network latency for links connected to this host
        self.cpu_frequency = cpu_frequency # Simulated CPU frequency
        self.cpu_threshold = cpu_threshold # CPU threshold for scheduling
        self.cpu_precision = cpu_precision # CPU precision for timing
        self.log_level = log_level # Logging level for this host
        self.pcap_directory = pcap_directory # Directory to store packet captures
        self.heart_beat_log_level = heart_beat_log_level # Log level for heartbeats
        self.heart_beat_interval = heart_beat_interval # Interval for heartbeats


    def __repr__(self):
        return (f"HostConfig(name='{self.name}', network_node_id={self.network_node_id}, "
                f"ip_addr='{self.ip_addr}', processes_count={len(self.processes)}, "
                f"bandwidth_up='{self.bandwidth_up}', bandwidth_down='{self.bandwidth_down}', "
                f"latency='{self.latency}', cpu_frequency={self.cpu_frequency}, ...)")

    def getProcessByPName(self, name:str):
        # the first arg in args
        for process in self.processes:
            if process.args and len(process.args) >0 and process.args[0] == name:
                return process
        return None

class ProcessConfig:
    """
    Represents the configuration for a single process to be run on a host.
    """
    def __init__(self, path, args=None, start_time=None, environment=None,
                 expected_final_state=None, log_level=None):
        self.path = path # Path to the executable
        self.args = args if args is not None else [] # List of arguments for the executable
        self.start_time = start_time # Simulation time at which the process should start
        self.environment = environment # Environment variables for the process
        self.expected_final_state = expected_final_state # Expected state of the process at simulation end
        self.log_level = log_level # Logging level for this process

    def __repr__(self):
        return (f"ProcessConfig(path='{self.path}', args={self.args}, start_time={self.start_time}, "
                f"environment='{self.environment}', expected_final_state='{self.expected_final_state}', "
                f"log_level='{self.log_level}')")


def parse_shadow_config(file_path: Path) -> 'ShadowConfig':
    """
    Parses a Shadow YAML configuration file and returns a Python object.

    Args:
        file_path (str): The path to the Shadow YAML configuration file.

    Returns:
        ShadowConfig: A Python object representing the configuration,
                      or None if the file cannot be parsed or is invalid.
    """
    if not os.path.exists(file_path):
        print(f"Error: Configuration file '{file_path}' not found.")
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file '{file_path}': {e}")
        return None
    except IOError as e:
        print(f"Error reading file '{file_path}': {e}")
        return None

    if not raw_config or not isinstance(raw_config, dict):
        print(f"Warning: Configuration file '{file_path}' is empty or not a valid YAML dictionary.")
        return ShadowConfig() # Return an empty config object

    # Parse general configuration
    parsed_general_config = None
    raw_general = raw_config.get('general')
    if isinstance(raw_general, dict):
        parsed_general_config = GeneralConfig(
            stop_time=raw_general.get('stop_time'),
            data_directory=raw_general.get('data_directory'),
            template_directory=raw_general.get('template_directory')
        )

    # Parse network configuration
    parsed_network_config = None
    raw_network = raw_config.get('network')
    if isinstance(raw_network, dict):
        raw_graph = raw_network.get('graph')
        if isinstance(raw_graph, dict):
            if raw_graph.get('type') and raw_graph.get('type') == 'gml':
                rel_gml_path = raw_graph.get('file').get('path')
                nf = file_path.parent.joinpath(rel_gml_path)
                parsed_network_config = Topology.from_gml(nf)
            else:
                logger.warning(f"Warning: yaml graph type '{raw_graph.get('type')}' is not a gml. We only support gml at the moment. Skipping network graph.")
        elif raw_graph is not None:
            logger.warning(f"Warning: 'network.graph' in '{file_path}' is not a dictionary. Skipping network graph.")
    elif raw_network is not None:
         logger.warning(f"Warning: 'network' in '{file_path}' is not a dictionary. Skipping network config.")


    # Parse hosts configuration
    parsed_hosts = {}
    raw_hosts = raw_config.get('hosts', {})
    if isinstance(raw_hosts, dict):
        for host_name, host_data in raw_hosts.items():
            if not isinstance(host_data, dict):
                print(f"Warning: Skipping invalid host entry '{host_name}' in '{file_path}'. Expected a dictionary.")
                continue

            parsed_processes = []
            raw_processes = host_data.get('processes', [])
            if isinstance(raw_processes, list):
                for proc_data in raw_processes:
                    if not isinstance(proc_data, dict):
                        print(f"Warning: Skipping invalid process entry for host '{host_name}' in '{file_path}'. Expected a dictionary.")
                        continue

                    path = proc_data.get('path')
                    if not path:
                        print(f"Warning: Skipping process with no path for host '{host_name}' in '{file_path}'.")
                        continue

                    args_str = proc_data.get('args')
                    parsed_args = []
                    if isinstance(args_str, str):
                        try:
                            # shlex.split handles quotes and spaces correctly for command-line arguments
                            parsed_args = shlex.split(args_str)
                        except ValueError as e:
                            # This can happen with unclosed quotes, for example
                            print(f"Warning: Could not parse args '{args_str}' for process '{path}' on host '{host_name}': {e}. Using raw string as a single argument.")
                            parsed_args = [args_str] # Fallback: treat the whole string as one argument
                    elif args_str is not None:
                         print(f"Warning: 'args' for process '{path}' on host '{host_name}' is not a string: '{args_str}'. Treating as no arguments.")


                    parsed_processes.append(ProcessConfig(
                        path=path,
                        args=parsed_args,
                        start_time=proc_data.get('start_time'),
                        environment=proc_data.get('environment'),
                        expected_final_state=proc_data.get('expected_final_state'),
                        log_level=proc_data.get('log_level')
                    ))
            elif raw_processes is not None:
                print(f"Warning: 'processes' for host '{host_name}' in '{file_path}' is not a list. Skipping processes for this host.")


            parsed_hosts[host_name] = HostConfig(
                name=host_name,
                network_node_id=host_data.get('network_node_id'),
                ip_addr=host_data.get('ip_addr'),
                processes=parsed_processes,
                bandwidth_up=host_data.get('bandwidth_up'),
                bandwidth_down=host_data.get('bandwidth_down'),
                latency=host_data.get('latency'),
                cpu_frequency=host_data.get('cpu_frequency'),
                cpu_threshold=host_data.get('cpu_threshold'),
                cpu_precision=host_data.get('cpu_precision'),
                log_level=host_data.get('log_level'),
                pcap_directory=host_data.get('pcap_directory'),
                heart_beat_log_level=host_data.get('heart_beat_log_level'),
                heart_beat_interval=host_data.get('heart_beat_interval')
            )
    elif raw_hosts is not None:
        print(f"Warning: 'hosts' in '{file_path}' is not a dictionary. Skipping all host configurations.")


    return ShadowConfig(general=parsed_general_config, network=parsed_network_config, hosts=parsed_hosts)
