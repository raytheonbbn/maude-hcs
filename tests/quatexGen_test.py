import pytest
import os
import yaml
from maude_hcs.parsers.quatexGenerator import QuatexGenerator
from maude_hcs.parsers.ymlconf import parse_adversary, Adversary


@pytest.fixture
def full_template_content():
    """Returns the content of a mock adversary_param.j2 for testing."""
    return """
// Adversary Parameter Template
ToDAvgQPS() = getToD(C,{{ start_time }},{{ w_qps }},{{ s_qps }},{{ k_qps }},{{ n_qps }})
ToDAvgQuerySize() = getToDAvgQuerySize(C,{{ start_time }},{{ w_qsize }},{{ s_qsize }},{{ k_qsize }},{{ n_qsize }})
ToDAvgResponseSize() = getToDAvgResponseSize(C,{{ start_time }},{{ w_respsize }},{{ s_respsize }},{{ k_respsize }},{{ n_respsize }})
ToDAvgUploadRate() = getToDAvgUploadRate(C,{{ start_time }},{{ w_uploadrate }},{{ s_uploadrate }},{{ k_uploadrate }},{{ n_uploadrate }})
ToDCumulativeNQueryPreNAT() = getToDCumulativeNQueryPreNAT(C,{{ N_query_pre_nat }})
ToDCumulativeNQueryPostNAT() = getToDCumulativeNQueryPostNAT(C,{{ N_query_post_nat }})
"""


@pytest.fixture
def setup_generator(tmp_path, full_template_content):
    """Creates a temporary template file and initializes the generator."""
    d = tmp_path / "templates"
    d.mkdir()
    p = d / "test_adversary.j2"
    p.write_text(full_template_content)
    return QuatexGenerator(str(p)), d


@pytest.fixture
def sample_yaml_content():
    """
    Returns the content of cp2_setup_example.yml as provided in the instructions.
    """
    return """
adversary_phase1:
  vantage_points:
    router_pre_nat:
      scripts:
        - name: cumulative/dns_query_count
          params:
            dns_q_threshold: 100
        - name: cumulative/dns_query_bytes
          params:
            dns_byte_threshold: 1000
        - name: cumulative/dns_response_bytes
          params:
            dns_resp_byte_threshold: 5000
        - name: cumulative/https_connection_count
          params:
            https_conn_threshold: 10
        - name: cumulative/https_upload_bytes
          params:
            https_upload_byte_threshold: 5000
    router_post_nat:
      scripts:
        - name: bin_loader
          params:
            json_path: "/baselines/cp2_setup_example.json" # baseline json
        - name: moving_average/average_dns_query_rate
          params:
            s: 10secs
            m: 6
            k: 1.15
            n: 3
        - name: moving_average/average_dns_query_size
          params:
            s: 10secs
            m: 6
            k: 1.15
            n: 3
        - name: moving_average/average_dns_response_size
          params:
            s: 10secs
            m: 6
            k: 1.15
            n: 3
        - name: moving_average/average_https_upload_rate
          params:
            s: 10secs
            m: 6
            k: 1.15
            n: 3
        - name: cumulative/dns_query_count
          params:
            dns_q_threshold: 200
        - name: cumulative/dns_query_bytes
          params:
            dns_byte_threshold: 1000
        - name: cumulative/dns_response_bytes
          params:
            dns_resp_byte_threshold: 5000
        - name: cumulative/https_connection_count
          params:
            https_conn_threshold: 10
        - name: cumulative/https_upload_bytes
          params:
            https_upload_byte_threshold: 5000
"""


@pytest.fixture
def sample_yaml_file(tmp_path, sample_yaml_content):
    p = tmp_path / "cp2_setup_example.yml"
    p.write_text(sample_yaml_content)
    return str(p)


def test_parse_adversary_and_generate(setup_generator, sample_yaml_file, tmp_path):
    """
    Integration test:
    1. Parse YAML using parse_adversary
    2. Convert to Generator Config using render_template
    3. Generate Quatex file
    """
    generator, _ = setup_generator
    output_file = tmp_path / "cp2_generated.quatex"

    # 1. Parse Adversary
    adversary_obj = parse_adversary(sample_yaml_file)

    # Verify parsing structure
    assert adversary_obj.router_pre_nat is not None
    assert adversary_obj.router_post_nat is not None
    scripts = adversary_obj.router_post_nat.get('scripts', [])
    assert len(scripts) > 0

    # 2. Render Template
    config = adversary_obj.render_template()

    # Verify extracted values
    # In YAML: k: 1.15, n: 3, m: 6, s: 10secs

    assert 'qps' in config
    qps_config = config['qps']
    assert qps_config['k'] == 1.15
    assert qps_config['n'] == 3
    assert qps_config['m'] == 6
    assert qps_config['s'] == 10  # Should be stripped of 'secs'

    # Verify cumulative thresholds
    assert config.get('N_query_pre_nat') == 100
    assert config.get('N_query_post_nat') == 200

    # Check upload rate
    assert 'uploadrate' in config
    assert config['uploadrate']['k'] == 1.15

    # 3. Generate File
    content = generator.generate_file(config, str(output_file))
    assert output_file.exists()

    # w = s * m = 10 * 6 = 60
    # Expected: getToD(C,0.0,60,10,1.15,3)
    assert "getToD(C,0.0,60,10,1.15,3)" in content
    # Check replacements
    assert "getToDCumulativeNQueryPreNAT(C,100)" in content
    assert "getToDCumulativeNQueryPostNAT(C,200)" in content


def test_parse_adversary_missing_values_safe(setup_generator, tmp_path):
    """Test that parser handles missing scripts gracefully."""
    yaml_content = """
    adversary_phase1:
      vantage_points:
        router_post_nat:
          scripts: []
    """
    p = tmp_path / "empty.yml"
    p.write_text(yaml_content)

    adv = parse_adversary(str(p))
    config = adv.render_template()

    # Should be empty except start_time
    assert config == {'start_time': 0.0}