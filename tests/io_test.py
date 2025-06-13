from pathlib import Path
import pytest
import json
import os

# Assume the code from the Canvas is saved in a file named 'config_loader.py'
from maude_hcs.lib.dns.io import CorporateIodineConfig

# --- Pytest Test Case Definition ---
FILENAME = '../use-cases/corporate-iodine.json'
TOPLEVELDIR = Path(os.path.dirname(__file__))
EXAMPLE_FILE_PATH = TOPLEVELDIR.joinpath(FILENAME)

@pytest.fixture
def sample_json_path():
    return EXAMPLE_FILE_PATH

def test_from_json_loading(sample_json_path):
    """
    Tests if the CorporateIodineConfig class can be instantiated correctly 
    from a JSON file.
    """
    config = CorporateIodineConfig.from_json(sample_json_path)
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
    assert p_params.nsResourceBounds is False  # Check the renamed field
    assert p_params.pacingTimeoutDelay == 0.05
    assert p_params.pacingTimeoutDelayMax == 0.07
    assert p_params.ackTimeoutDelay == 1.0

    # Underlying Network
    u_net = config.underlying_network
    assert u_net.module == "dns"
    assert u_net.populate_resolver_cache is True
    assert u_net.record_ttl == 3600
    assert u_net.addr_prefix == "addrNS"
    assert u_net.everythingelse_name == "example"
    assert u_net.everythingelse_num_records == 2
    assert u_net.pwnd2_name == "pwnd2"
    assert u_net.pwnd2_base_name == "pwnd2.com."
    assert u_net.resolver_name == "rAddr"
    assert u_net.corporate_name == "corporate"
    assert u_net.nodes == {}
    assert len(u_net.links) == 10
    assert u_net.links["corporate_name->resolver_name"].latency == 0.005
    assert u_net.links["corporate_name->resolver_name"].jitter == 0.0
    assert u_net.links["corporate_name->resolver_name"].loss == 0.0

    # Weird Network
    w_net = config.weird_network
    assert w_net.module == "iodine"
    assert w_net.client_address == "iodineC"
    assert w_net.client_weird_qtype == "a"
    assert w_net.monitor_address == "monAddr"
    assert len(w_net.links) == 2
    
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
    bg_traffic = app.background_traffic
    assert bg_traffic.num_paced_clients == 1
    assert bg_traffic.paced_client_address_prefix == "pcAddr"
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
    """
    Tests if the to_json method correctly exports the dataclass to a JSON file,
    including handling the special 'nsResourceBounds?' key.
    """
    # Load the initial config
    config = CorporateIodineConfig.from_json(sample_json_path)
    
    # Define an output path in the temporary directory
    output_path = tmp_path / "output_config.json"
    
    # Export it
    config.to_json(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path)
    
    # Load the exported data and check its contents
    with open(output_path, 'r') as f:
        data = json.load(f)
        
    assert data["name"] == "corporate_iodine"
    assert "nsResourceBounds?" in data["probabilistic_parameters"]
    assert data["probabilistic_parameters"]["nsResourceBounds?"] is False
    assert "nsResourceBounds" not in data["probabilistic_parameters"] # Make sure the python name is not there
    assert data["underlying_network"]["links"]["corporate_name->resolver_name"]["latency"] == 0.005

def test_json_roundtrip(sample_json_path, tmp_path):
    """
    Tests that loading a JSON file and immediately saving it again results
    in an identical JSON structure. This is a "roundtrip" test.
    """
    # 1. Load the original config
    config_original = CorporateIodineConfig.from_json(sample_json_path)
    
    # 2. Define a path for the new file and save it
    roundtrip_path = tmp_path / "roundtrip_config.json"
    config_original.to_json(roundtrip_path)
    
    # 3. Load the newly created file
    config_roundtrip = CorporateIodineConfig.from_json(roundtrip_path)
    
    # 4. Compare the original loaded object with the round-tripped one
    assert config_original == config_roundtrip
