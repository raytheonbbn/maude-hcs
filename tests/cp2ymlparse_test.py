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


import pytest

from maude_hcs.parsers.dnshcsconfig import DNSHCSConfig2
from maude_hcs.parsers.ymlconf import YmlConf, CoverImage

TEST_YAML_CONTENT = """
self_path: /src/landing/testing_configs/cp2_setup_example.yml

#TGEN SECTION
enable_tgen: true
tgen_clients:
    configs:
      tgen_request_section_1:
        total: 5
        type: mastodon
        profiles:
          mastodon_lurker:
            profile: config_lurker_1.json
            percent: 30
          mastodon_influncer:
            profile: config_influencer_1.json
            percent: 70
      tgen_request_section_2:
        total: 5
        type: dns
        profiles:
          dns_lurker:
            profile: config_slow_1.json
            percent: 30
          dns_influncer:
            profile: config_fast_1.json
            percent: 70
      tgen_request_section_3:
        total: 1
        type: mastodon_monitor
        profiles:
          monitor:
            profile: config_monitor.json
            percent: 100

#MASTODON SECTION
mastodon_server:
  server_fqdn: "mastodon.pwnd.com"

#APPLICATION SECTION
application:
  destini:
    jpeg_covers: jpeg-covers-25-jpg.tar
  iodine:
    max_query_length: 255
    max_response_size: 512
  alice:
    mastodon_user: alice
    raceboat_prof_config: client_config.json
    raceboat_prof: client_timeline_builder.json
  bob:
    mastodon_user: bob
    raceboat_prof_config: server_config.json
    raceboat_prof: server_timeline_builder.json

# BASELINE
adversary_phase0:
  vantage_points:
    router_post_nat:
      scripts:
        - name: bin_calculator

#ZEEK (ACTUAL)
adversary_phase1:
  vantage_points:
    router_pre_nat:
      scripts:
        - name: cumulative/dns_query_count

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


@pytest.fixture
def yml_conf_file(tmp_path):
    """
    Fixture that creates a temporary YAML configuration file
    and returns its path as a string.
    tmp_path is a built-in pytest fixture providing a unique temporary directory.
    """
    config_file = tmp_path / "cp2_setup_example.yml"
    config_file.write_text(TEST_YAML_CONTENT)
    return str(config_file)


def test_parse_yml_conf(yml_conf_file):
    # 1. Parse the file
    conf = YmlConf(yml_conf_file)

    # 2. Verify Underlying Network
    assert conf.underlying_network.server_fqdn == "mastodon.pwnd.com"

    # 3. Verify Application - Alice
    assert conf.application.alice.mastodon_user == "alice"
    assert conf.application.alice.raceboat_prof_config == "client_config.json"
    assert conf.application.alice.raceboat_prof == "client_timeline_builder.json"

    # 4. Verify Application - Bob
    assert conf.application.bob.mastodon_user == "bob"
    assert conf.application.bob.raceboat_prof_config == "server_config.json"
    assert conf.application.bob.raceboat_prof == "server_timeline_builder.json"

    # 5. Verify Application - Iodine
    assert conf.application.iodine.max_query_length == 255
    assert conf.application.iodine.max_response_size == 512

    # 6. Verify Application - Destini
    assert len(conf.application.destini.jpeg_covers) == 30
    assert conf.application.destini.jpeg_covers[0] == CoverImage(name='101502', capacity_bytes=3000, size_bytes=37794)

    # 7. Verify Adversary
    assert 'vantage_points' in conf.adversary.baseline
    assert 'router_post_nat' in conf.adversary.baseline['vantage_points']

    assert 'vantage_points' in conf.adversary.actual
    assert 'router_pre_nat' in conf.adversary.actual['vantage_points']

    # 8. Verify Background Traffic (TGen)
    tgen = conf.background_traffic

    def find_config(c_type, c_json):
        return next((c for c in tgen if c[0] == c_type and c[1] == c_json), None)

    lurker_1 = find_config('mastodon', 'config_lurker_1.json')
    assert lurker_1 is not None
    assert lurker_1[2] == 2  # Count

    influencer_1 = find_config('mastodon', 'config_influencer_1.json')
    assert influencer_1 is not None
    assert influencer_1[2] == 3  # Count (Adjusted from 4)

    lurker_dns = find_config('dns', 'config_slow_1.json')
    assert lurker_dns is not None
    assert lurker_dns[2] == 2

    influencer_dns = find_config('dns', 'config_fast_1.json')
    assert influencer_dns is not None
    assert influencer_dns[2] == 3  # Count (Adjusted from 4)

    monitor = find_config('mastodon_monitor', 'config_monitor.json')
    assert monitor is not None
    assert monitor[2] == 1


def test_topology_parsing(yml_conf_file):
    conf = YmlConf(yml_conf_file)

    # Verify basic topology stats
    assert len(conf.network.links) == 14

    # Check specific link existence
    link_labels = [l.label for l in conf.network.links]
    assert "from public_dns to router" in link_labels
    assert "from router to public_dns" in link_labels
    assert "from public_dns to root_dns" in link_labels

    # Check Node Properties
    public_dns_node = conf.network.getNodebyLabel("public_dns")
    assert public_dns_node is not None
    assert public_dns_node.address == "public-dns"

    # Check Latency Parsing
    link_obj = next(l for l in conf.network.links if l.src_label == "public_dns" and l.dst_label == "router")
    # 15ms = 0.015s. Using pytest.approx for floating point comparison
    assert link_obj.latency == pytest.approx(0.015)

    #test_parser_nodes_count
    assert len(conf.network.nodes) == 7, f"expected 7 nodes but found {len(conf.network.nodes)}"

    # test_parser_nodes_list
    nodes_string = "[Node(id=0, label='public_dns', address='public-dns', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=1, label='root_dns', address='root-dns', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=2, label='tld_dns', address='tld-dns', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=3, label='auth_dns', address='auth-dns', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=4, label='router', address='router', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=5, label='mastodon_proxy', address='mastodon-proxy', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit'), Node(id=6, label='user_bob', address='user-bob', ip_address='', host_bandwidth_up='1 Gbit', host_bandwidth_down='1 Gbit')]"
    assert str(conf.network.nodes) == nodes_string

    # test_parser_edges_list
    links_string = "[Link(src_id=0, src_label='public_dns', dst_id=1, dst_label='root_dns', label='from public_dns to root_dns', latency=0.01, jitter=0.0, loss=0.0), Link(src_id=1, src_label='root_dns', dst_id=0, dst_label='public_dns', label='from root_dns to public_dns', latency=0.01, jitter=0.0, loss=0.0), Link(src_id=0, src_label='public_dns', dst_id=2, dst_label='tld_dns', label='from public_dns to tld_dns', latency=0.01, jitter=0.0, loss=0.0), Link(src_id=2, src_label='tld_dns', dst_id=0, dst_label='public_dns', label='from tld_dns to public_dns', latency=0.01, jitter=0.0, loss=0.0), Link(src_id=0, src_label='public_dns', dst_id=3, dst_label='auth_dns', label='from public_dns to auth_dns', latency=0.025, jitter=0.02, loss=0.0), Link(src_id=3, src_label='auth_dns', dst_id=0, dst_label='public_dns', label='from auth_dns to public_dns', latency=0.025, jitter=0.02, loss=0.0), Link(src_id=0, src_label='public_dns', dst_id=4, dst_label='router', label='from public_dns to router', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=4, src_label='router', dst_id=0, dst_label='public_dns', label='from router to public_dns', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=5, src_label='mastodon_proxy', dst_id=4, dst_label='router', label='from mastodon_proxy to router', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=4, src_label='router', dst_id=5, dst_label='mastodon_proxy', label='from router to mastodon_proxy', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=6, src_label='user_bob', dst_id=5, dst_label='mastodon_proxy', label='from user_bob to mastodon_proxy', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=5, src_label='mastodon_proxy', dst_id=6, dst_label='user_bob', label='from mastodon_proxy to user_bob', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=6, src_label='user_bob', dst_id=0, dst_label='public_dns', label='from user_bob to public_dns', latency=0.015, jitter=0.0, loss=0.0), Link(src_id=0, src_label='public_dns', dst_id=6, dst_label='user_bob', label='from public_dns to user_bob', latency=0.015, jitter=0.0, loss=0.0)]"
    assert str(conf.network.links) == links_string

    # test_edge_attributes(config_obj)
    """Verify attributes for each edge."""
    found = False
    for link in conf.network.links:
        if link.src_id == 6 and link.dst_id == 5:
            #Link(src_id=6, src_label='user_bob', dst_id=5, dst_label='mastodon_proxy', label='from user_bob to mastodon_proxy', latency=0.015, jitter=0.0, loss=0.0),
            assert link.label == "from user_bob to mastodon_proxy"
            assert link.latency == 0.015
            assert link.jitter == 0.0
            assert link.loss == 0.0
            found = True
    assert found, 'expecting a link from 6 to 5'

def test_hcsconfig2(yml_conf_file):
    conf = DNSHCSConfig2.from_yml(yml_conf_file)
    print(conf.to_json(indent=4))
