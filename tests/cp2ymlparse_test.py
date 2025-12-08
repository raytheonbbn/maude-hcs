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

import os
import pytest
from pathlib import Path

from maude_hcs.parsers.graph import Topology
from maude_hcs.parsers.shadowconf import ShadowConfig, GeneralConfig, HostConfig, ProcessConfig, parse_shadow_config
# --- Pytest Test Case Definition ---
EXAMPLE_YAML_CONTENT = """
#TC NETWORKING
weird_network_section:
    - src: public_dns
      dst: router
      net_params:
        latency: "15ms"
        jitter: "0ms"
        loss: 0.0

    - src: router
      dst: public_dns
      net_params:
        latency: "15ms"
        jitter: "0ms"
        loss: 0.0
 
    - src: mastodon_proxy
      dst: router
      net_params:
        latency: "15ms"
        jitter: "0ms"
        loss: 0.0

    - src: router
      dst: mastodon_proxy
      net_params:
        latency: "15ms"
        jitter: "0ms"
        loss: 0.0
    
    - src: user_bob
      dst: mastodon_proxy
      net_params:
        latency: "15ms"
        jitter: "0ms"
        loss: 0.0

    - src: mastodon_proxy
      dst: user_bob
      net_params:
        latency: "15ms"
        jitter: "0ms"
        loss: 0.0

    - src: user_bob
      dst: public_dns
      net_params:
        latency: "15ms"
        jitter: "0ms"
        loss: 0.0

    - src: public_dns
      dst: user_bob 
      net_params:
        latency: "15ms"
        jitter: "0ms"
        loss: 0.0

# tc links
network_section:
    - src: public_dns
      dst: root_dns
      net_params:
        latency: "10ms"
        jitter: "0ms"
        loss: 0.0

    - src: root_dns
      dst: public_dns
      net_params:
        latency: "10ms"
        jitter: "0ms"
        loss: 0.0
    
    - src: public_dns
      dst: tld_dns
      net_params:
        latency: "10ms"
        jitter: "0ms"
        loss: 0.0

    - src: tld_dns
      dst: public_dns
      net_params:
        latency: "10ms"
        jitter: "0ms"
        loss: 0.0

    - src: public_dns
      dst: auth_dns
      net_params:
        latency: "25ms"
        jitter: "20ms"
        loss: 0.0

    - src: auth_dns
      dst: public_dns
      net_params:
        latency: "25ms"
        jitter: "20ms"
        loss: 0.0
"""
FILENAME = 'tmp_yml__testfile.yaml'
TOPLEVELDIR = Path(os.path.dirname(__file__))
EXAMPLE_FILE_PATH = TOPLEVELDIR.joinpath(FILENAME)

@pytest.fixture
def config_obj():
    """Pytest fixture to create and parse the example YAML file."""
    with open(EXAMPLE_FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(EXAMPLE_YAML_CONTENT)
    
    parsed_config = Topology.from_yml(EXAMPLE_FILE_PATH)
    
    yield parsed_config # Provide the parsed config to the test    
    
    # Teardown: Remove the example YAML file after the test
    if os.path.exists(EXAMPLE_FILE_PATH):
        os.remove(EXAMPLE_FILE_PATH)

def test_parser_instantiation(config_obj):
    """Test that the parser returns a ShadowConfig object."""
    assert config_obj is not None, "Parser returned None."
    assert isinstance(config_obj, Topology), "Parsed object is not a Topology instance."

def test_parser_nodes_count(config_obj):
    assert config_obj is not None, "Parser returned None."
    assert len(config_obj.nodes) == 7, f"expected 7 nodes but found {len(config_obj.nodes)}"

def test_parser_nodes_list(config_obj):
    assert config_obj is not None, "Parser returned None."
    nodes_string = "[Node(id=0, label='public_dns', address='public-dns', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=1, label='root_dns', address='root-dns', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=2, label='tld_dns', address='tld-dns', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=3, label='auth_dns', address='auth-dns', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=4, label='router', address='router', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=5, label='mastodon_proxy', address='mastodon-proxy', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=6, label='user_bob', address='user-bob', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit')]"
    assert str(config_obj.nodes) == nodes_string

def test_parser_edges_list(config_obj):
    assert config_obj is not None, "Parser returned None."
    links_string = "[Link(src_id=0, src_label='public_dns', dst_id=1, dst_label='root_dns', label='from public_dns to root_dns', latency=0.01, jitter=0.0, loss=0.0), Link(src_id=1, src_label='root_dns', dst_id=0, dst_label='public_dns', label='from root_dns to public_dns', latency=0.01, jitter=0.0, loss=0.0), Link(src_id=0, src_label='public_dns', dst_id=2, dst_label='tld_dns', label='from public_dns to tld_dns', latency=0.01, jitter=0.0, loss=0.0), Link(src_id=2, src_label='tld_dns', dst_id=0, dst_label='public_dns', label='from tld_dns to public_dns', latency=0.01, jitter=0.0, loss=0.0), Link(src_id=0, src_label='public_dns', dst_id=3, dst_label='auth_dns', label='from public_dns to auth_dns', latency=0.025, jitter=0.02, loss=0.0), Link(src_id=3, src_label='auth_dns', dst_id=0, dst_label='public_dns', label='from auth_dns to public_dns', latency=0.025, jitter=0.02, loss=0.0), Link(src_id=0, src_label='public_dns', dst_id=4, dst_label='router', label='from public_dns to router', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=4, src_label='router', dst_id=0, dst_label='public_dns', label='from router to public_dns', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=5, src_label='mastodon_proxy', dst_id=4, dst_label='router', label='from mastodon_proxy to router', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=4, src_label='router', dst_id=5, dst_label='mastodon_proxy', label='from router to mastodon_proxy', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=6, src_label='user_bob', dst_id=5, dst_label='mastodon_proxy', label='from user_bob to mastodon_proxy', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=5, src_label='mastodon_proxy', dst_id=6, dst_label='user_bob', label='from mastodon_proxy to user_bob', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=6, src_label='user_bob', dst_id=0, dst_label='public_dns', label='from user_bob to public_dns', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=0, src_label='public_dns', dst_id=6, dst_label='user_bob', label='from public_dns to user_bob', latency=0.015, jitter=0.0, loss=0.0)]"
    assert str(config_obj.links) == links_string

def test_edge_attributes(config_obj):
    """Verify attributes for each edge."""
    found = False
    for link in config_obj.links:
        if link.src_id == 6 and link.dst_id == 5:
            #Link(src_id=6, src_label='user_bob', dst_id=5, dst_label='mastodon_proxy', label='from user_bob to mastodon_proxy', latency=0.015, jitter=0.0, loss=0.0),
            assert link.label == "from user_bob to mastodon_proxy"
            assert link.latency == 0.015
            assert link.jitter == 0.0
            assert link.loss == 0.0
            found = True
    assert found, 'expecting a link from 6 to 5'