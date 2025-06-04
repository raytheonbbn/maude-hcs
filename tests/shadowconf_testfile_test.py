import os
import pytest
from pathlib import Path
from maude_hcs.parsers.shadowconf import ShadowConfig, GeneralConfig, NetworkConfig, HostConfig, ProcessConfig, parse_shadow_config

# --- Pytest Test Case Definition ---
FILENAME = 'testfile.yaml'
TOPLEVELDIR = Path(os.path.dirname(__file__))
EXAMPLE_FILE_PATH = TOPLEVELDIR.joinpath(FILENAME)

@pytest.fixture
def config_obj():
    parsed_config = parse_shadow_config(EXAMPLE_FILE_PATH)
    yield parsed_config # Provide the parsed config to the test    

def test_parser_instantiation(config_obj):
    """Test that the parser returns a ShadowConfig object."""
    assert config_obj is not None, "Parser returned None."
    assert isinstance(config_obj, ShadowConfig), "Parsed object is not a ShadowConfig instance."

def test_general_config_parsing(config_obj):
    """Test parsing of the 'general' section."""
    assert config_obj.general is None, "'general' section was not specified."    

def test_network_config_parsing(config_obj):
    """Test parsing of the 'network' section."""
    assert config_obj.network is not None, "'network' section not parsed."
    assert isinstance(config_obj.network, NetworkConfig)
    assert config_obj.network.graph_type == "gml"
    assert config_obj.network.graph_path == "./file.gml"

def test_hosts_exist(config_obj):
    """Test that hosts are parsed and correct host names are present."""
    assert config_obj.hosts is not None, "'hosts' section not parsed."
    assert isinstance(config_obj.hosts, dict)
    assert "A" in config_obj.hosts
    assert "hostG" in config_obj.hosts
    assert "perf" in config_obj.hosts
    assert len(config_obj.hosts) == 8

def test_hostF_config(config_obj):
    """Test specific configuration."""
    assert "hostF" in config_obj.hosts
    server0 = config_obj.hosts["hostF"]
    assert isinstance(server0, HostConfig)
    assert server0.name == "hostF"
    assert server0.network_node_id == 5
    assert len(server0.processes) == 3

def test_hostF_process1_args(config_obj):
    """Test argument parsing for the first process."""
    server0 = config_obj.hosts["hostF"]
    process1 = server0.processes[0]
    assert isinstance(process1, ProcessConfig)
    assert process1.path == "application:"
    expected_args = ["tail", "-f", "/dev/null"]
    assert process1.args == expected_args

def test_hostF_process2_args(config_obj):
    """Test argument parsing for the second process."""
    server0 = config_obj.hosts["hostF"]
    process2 = server0.processes[1]
    assert isinstance(process2, ProcessConfig)
    assert process2.path == "."
    assert process2.args == ["mydaemon", "-f", "-c", "-P", "pass", "10.0.0.1", "x.y.com"]

def test_hostF_process3_args(config_obj):
    """Test argument parsing for the second process."""
    server0 = config_obj.hosts["hostF"]
    process2 = server0.processes[2]
    assert isinstance(process2, ProcessConfig)
    assert process2.path == "."
    assert process2.args == ["python3", "server.py", "-l", "data/logs/", "-o", "data/output/"]