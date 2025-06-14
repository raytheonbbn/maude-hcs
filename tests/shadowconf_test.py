import os
import pytest
from pathlib import Path
from maude_hcs.parsers.shadowconf import ShadowConfig, GeneralConfig, HostConfig, ProcessConfig, parse_shadow_config
# --- Pytest Test Case Definition ---
EXAMPLE_YAML_CONTENT = """
general:
  stop_time: 300s # Stop after 5 minutes
  data_directory: shadow.data.%s # %s will be replaced by host name
  template_directory: ~/.shadow/share/shadow/examples/config/hosts

network:
  graph:
    type: sometype
    file:
        path: /path/to/your/network.gml
        compression: null

hosts:
  server0:
    network_node_id: 0
    ip_addr: "10.0.0.1"
    bandwidth_up: "100 Mbit"
    bandwidth_down: "100 Mbit"
    latency: "5 ms"
    cpu_frequency: 2000 # MHz
    cpu_threshold: "1 ms"
    cpu_precision: "1 us"
    log_level: "info"
    pcap_directory: "server0.pcap"
    heart_beat_log_level: "message"
    heart_beat_interval: "1 s"
    processes:
      - path: /usr/bin/my_server
        args: "--port 8080 --config /etc/server.conf --mode production --message 'Hello World'"
        start_time: 1s
        environment: "LD_PRELOAD=/path/to/my_lib.so CUSTOM_VAR=value"
        expected_final_state: running
        log_level: "debug"
      - path: /usr/bin/utility_tool
        args: "status --verbose" # Simple args
        start_time: 2s

  client1:
    network_node_id: 1
    ip_addr: "10.0.0.2"
    bandwidth_up: "50 Mbit" # Different bandwidth
    bandwidth_down: "50 Mbit"
    processes:
      - path: /usr/bin/my_client
        args: "connect server0:8080 --user 'test user' --timeout 30"
        start_time: 5s
      - path: /usr/bin/ping_check # Process with no args
        start_time: 6s
        log_level: "warning"
      - path: /usr/bin/faulty_args_process
        args: "unclosed_quote 'is bad" # Intentionally malformed for shlex to test warning
        start_time: 7s
      - path: /usr/bin/no_args_at_all # Process with args field missing
        start_time: 8s


  router5:
    network_node_id: 5 # Example of a host that might not run processes (e.g., a router)
    # No IP address specified, might be a pure router
    log_level: "critical"
"""
FILENAME = 'tmp_testfile.yaml'
TOPLEVELDIR = Path(os.path.dirname(__file__))
EXAMPLE_FILE_PATH = TOPLEVELDIR.joinpath(FILENAME)

@pytest.fixture
def config_obj():
    """Pytest fixture to create and parse the example YAML file."""
    with open(EXAMPLE_FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(EXAMPLE_YAML_CONTENT)
    
    parsed_config = parse_shadow_config(EXAMPLE_FILE_PATH)
    
    yield parsed_config # Provide the parsed config to the test    
    
    # Teardown: Remove the example YAML file after the test
    if os.path.exists(EXAMPLE_FILE_PATH):
        os.remove(EXAMPLE_FILE_PATH)

def test_parser_instantiation(config_obj):
    """Test that the parser returns a ShadowConfig object."""
    assert config_obj is not None, "Parser returned None."
    assert isinstance(config_obj, ShadowConfig), "Parsed object is not a ShadowConfig instance."

def test_general_config_parsing(config_obj):
    """Test parsing of the 'general' section."""
    assert config_obj.general is not None, "'general' section not parsed."
    assert isinstance(config_obj.general, GeneralConfig)
    assert config_obj.general.stop_time == "300s"
    assert config_obj.general.data_directory == "shadow.data.%s"
    assert config_obj.general.template_directory == "~/.shadow/share/shadow/examples/config/hosts"

def test_network_config_parsing(config_obj):
    """Test parsing of the 'network' section."""
    assert config_obj.network is None, "We didnt expect to parse non gml network"

def test_hosts_exist(config_obj):
    """Test that hosts are parsed and correct host names are present."""
    assert config_obj.hosts is not None, "'hosts' section not parsed."
    assert isinstance(config_obj.hosts, dict)
    assert "server0" in config_obj.hosts
    assert "client1" in config_obj.hosts
    assert "router5" in config_obj.hosts
    assert len(config_obj.hosts) == 3

def test_server0_config(config_obj):
    """Test specific configuration for 'server0'."""
    assert "server0" in config_obj.hosts
    server0 = config_obj.hosts["server0"]
    assert isinstance(server0, HostConfig)
    assert server0.name == "server0"
    assert server0.network_node_id == 0
    assert server0.ip_addr == "10.0.0.1"
    assert server0.bandwidth_up == "100 Mbit"
    assert server0.cpu_frequency == 2000
    assert server0.log_level == "info"
    assert server0.heart_beat_interval == "1 s"
    assert len(server0.processes) == 2

def test_server0_process1_args(config_obj):
    """Test argument parsing for the first process on 'server0'."""
    server0 = config_obj.hosts["server0"]
    process1 = server0.processes[0]
    assert isinstance(process1, ProcessConfig)
    assert process1.path == "/usr/bin/my_server"
    expected_args = ["--port", "8080", "--config", "/etc/server.conf", "--mode", "production", "--message", "Hello World"]
    assert process1.args == expected_args
    assert process1.start_time == "1s"
    assert process1.environment == "LD_PRELOAD=/path/to/my_lib.so CUSTOM_VAR=value"
    assert process1.expected_final_state == "running"
    assert process1.log_level == "debug"

def test_server0_process2_args(config_obj):
    """Test argument parsing for the second process on 'server0'."""
    server0 = config_obj.hosts["server0"]
    process2 = server0.processes[1]
    assert isinstance(process2, ProcessConfig)
    assert process2.path == "/usr/bin/utility_tool"
    assert process2.args == ["status", "--verbose"]
    assert process2.start_time == "2s"

def test_client1_config(config_obj):
    """Test specific configuration for 'client1'."""
    assert "client1" in config_obj.hosts
    client1 = config_obj.hosts["client1"]
    assert isinstance(client1, HostConfig)
    assert client1.network_node_id == 1
    assert client1.ip_addr == "10.0.0.2"
    assert len(client1.processes) == 4 # Includes faulty and no_args

def test_client1_process_no_args_field(config_obj):
    """Test a process on client1 that has no 'args' field in YAML."""
    client1 = config_obj.hosts["client1"]
    # The process '/usr/bin/no_args_at_all' is the 4th one (index 3)
    process_no_args_field = client1.processes[3]
    assert process_no_args_field.path == "/usr/bin/no_args_at_all"
    assert process_no_args_field.args == [] # Should default to empty list

def test_client1_process_empty_args_value(config_obj):
    """Test a process on client1 that has an 'args' field but it's effectively empty or null."""
    # This corresponds to '/usr/bin/ping_check' which has no args string
    client1 = config_obj.hosts["client1"]
    ping_check_process = client1.processes[1] # Second process
    assert ping_check_process.path == "/usr/bin/ping_check"
    assert ping_check_process.args == [] # Should be an empty list

def test_faulty_args_parsing(config_obj):
    """Test how faulty arguments (e.g., unclosed quote) are handled."""
    client1 = config_obj.hosts["client1"]
    faulty_process = client1.processes[2] # Third process
    assert faulty_process.path == "/usr/bin/faulty_args_process"
    # shlex.split with an unclosed quote will raise ValueError,
    # our parser falls back to treating the whole string as one argument.
    assert faulty_process.args == ["unclosed_quote 'is bad"]