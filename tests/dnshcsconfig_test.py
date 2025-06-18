#!/usr/bin/env python
# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# PWNDD Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# Contract No: HR00112590083
# Contractor Name: RTX BBN Technologies Inc.
# Contractor Address: 10 Moulton Street, Cambridge, Massachusetts 02138
#
# The U.S. Government's rights to use, modify, reproduce, release, perform,
# display, or disclose these technical data and software are defined in the
# Article VII: Data Rights clause of the OTA.
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
# contained herein.
#
# MAUDE_HCS: end

from pathlib import Path
import pytest
import json
import os

# Assume the code from the Canvas is saved in a file named 'config_loader.py'
from maude_hcs.parsers.dnshcsconfig import DNSHCSConfig

# --- Pytest Test Case Definition ---
FILENAME = '../use-cases/corporate-iodine-conf.json'
TOPLEVELDIR = Path(os.path.dirname(__file__))
EXAMPLE_FILE_PATH = TOPLEVELDIR.joinpath(FILENAME)

@pytest.fixture
def sample_json_path():
    return EXAMPLE_FILE_PATH

def test_from_file_loading(sample_json_path):
    """
    Tests if the HCSConfig class can be instantiated correctly 
    from a JSON file.
    """
    config = DNSHCSConfig.from_file(sample_json_path)
    assert config.name == "corporate_iodine"
    # Nondeterministic Parameters
    nd_params = config.nondeterministic_parameters
    assert nd_params.fileSize == 1000
    assert nd_params.packetSize == 530
    assert nd_params.packetOverhead == 33
    assert nd_params.maxMinimiseCount == 0
    assert nd_params.maxFragmentLen == 100
    assert nd_params.maxFragmentTx == 20

    # Probabilistic Parameters
    p_params = config.probabilistic_parameters
    assert p_params.maxPacketSize == 530
    assert p_params.pacingTimeoutDelay == 0.05
    assert p_params.pacingTimeoutDelayMax == 0.07
    assert p_params.ackTimeoutDelay == 1.0


    # Underlying Network
    u_net = config.underlying_network
    assert u_net.module == "dns"
    assert u_net.populate_resolver_cache is True
    assert u_net.record_ttl == 3600
    assert u_net.addr_prefix == "addr-"
    assert u_net.everythingelse_name == "internet-dns"
    assert u_net.everythingelse_num_records == 2
    assert u_net.pwnd2_name == "application-server"
    assert u_net.pwnd2_domain == "pwnd2.com."
    assert u_net.tld_domain == "com."
    assert u_net.everythingelse_domain == "internet.com."
    assert u_net.corporate_domain == "corporate.com."
    assert u_net.resolver_name == "public-dns"
    assert u_net.corporate_name == "local-dns"
    assert u_net.root_name == "root-dns"
    assert u_net.tld_name == "tld-dns"

    # Topology
    topo = config.topology
    assert len(topo.nodes) == 8
    assert len(topo.links) == 7    

    # Weird Network
    w_net = config.weird_network
    assert w_net.module == "iodine"
    assert w_net.client_name == "application-client"
    assert w_net.client_weird_qtype == "a"
    assert w_net.severWResponseTTL == 0.0
    assert w_net.monitor_address == "monAddr"    
    
    # Application
    app = config.application
    assert app.module == "simplex"
    assert app.send_app_address == "Alice"
    assert app.overwrite_queue is True
    assert app.send_app_queue_pkt_sizes == [200, 200, 100, 10]
    assert app.app_start_send_time == 1.0
    assert app.rcv_app_address == "Bob"
    assert app.include_dns_client is False    

    # Background Traffic (nested in Application)
    bg_traffic = config.background_traffic
    assert bg_traffic.num_paced_clients == 1
    assert bg_traffic.paced_client_name == "dnsperf"
    assert bg_traffic.paced_client_Tlimit == 2
    assert bg_traffic.paced_client_MaxQPS == 50

    # Output
    out = config.output
    assert out.directory == "results"
    assert out.result_format == "maude"
    assert out.save_output is True
    assert out.force_save is True
    assert out.visualize is False
    assert len(out.preamble) == 3

def test_to_json_exporting(sample_json_path, tmp_path):
    # Load the initial config
    config = DNSHCSConfig.from_file(sample_json_path)
    
    # Define an output path in the temporary directory
    output_path = tmp_path / "output_config.json"
    
    # Export it
    config.save(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path)
    # # Load the exported data and check its contents
    # with open(output_path, 'r') as f:
    #     data = json.load(f)
        
    # assert data["name"] == "corporate_iodine"    
    # assert data["probabilistic_parameters"]["nsResourceBounds?"] is False
    # assert "nsResourceBounds" not in data["probabilistic_parameters"] # Make sure the python name is not there
    # assert data["underlying_network"]["links"]["corporate_name->resolver_name"]["latency"] == 0.005

def test_json_roundtrip(sample_json_path, tmp_path):
    """
    Tests that loading a JSON file and immediately saving it again results
    in an identical JSON structure. This is a "roundtrip" test.
    """
    # 1. Load the original config
    config_original = DNSHCSConfig.from_file(sample_json_path)
    
    # 2. Define a path for the new file and save it
    roundtrip_path = tmp_path / "roundtrip_config.json"
    print(roundtrip_path)
    config_original.save(roundtrip_path)
    
    # 3. Load the newly created file
    config_roundtrip = DNSHCSConfig.from_file(roundtrip_path)
    
    # 4. Compare the original loaded object with the round-tripped one
    assert config_original == config_roundtrip
