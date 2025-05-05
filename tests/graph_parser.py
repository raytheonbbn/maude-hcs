import pytest
import networkx as nx
import os
import tempfile
import logging

from maude_hcs.parsers.graph import parse_shadow_gml, get_edge_delays_by_label

# GML content identical to the example file provided earlier
# Embedding it here makes the test self-contained
TEST_GML_CONTENT = """
graph [
  directed 1
  id "ExampleNet"
  label "A small test network for Shadow parsing"
  node [ id 0 label "HostA" asn 100 ip_addr "10.0.0.1" host_bandwidth_up 100000000 host_bandwidth_down 100000000 ]
  node [ id 1 label "Router1" asn 200 ]
  node [ id 2 label "HostB" asn 100 ip_addr "10.0.0.2" host_bandwidth_up 50000000 host_bandwidth_down 100000000 ]
  edge [ source 0 target 1 label "Link_HostA_to_Router1" latency 10.5 jitter 1.2 packet_loss 0.01 ]
  edge [ source 1 target 0 label "Link_Router1_to_HostA" latency 10.5 jitter 0.0 packet_loss 0.0 ]
  edge [ source 1 target 2 label "Link_Router1_to_HostB" latency 15.0 jitter 2.0 packet_loss 0.005 ]
  edge [ source 2 target 1 label "Link_HostB_to_Router1" latency 15.0 jitter 1.8 packet_loss 0.008 ]
]
"""

# --- Pytest Fixtures ---

@pytest.fixture(scope="session") # Run once per test session
def gml_file_path():
    """Fixture to create a temporary GML file and yield its path."""
    # Create a temporary file that persists until the fixture scope ends
    temp_gml_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.gml', encoding='utf-8')
    temp_gml_file.write(TEST_GML_CONTENT)
    temp_gml_file.close() # Close the file handle, path remains valid
    file_path = temp_gml_file.name
    logging.info(f"Created temporary GML file for testing: {file_path}")

    yield file_path # Provide the path to the tests

    # Teardown: Remove the file after the test session finishes
    try:
        os.remove(file_path)
        logging.info(f"Removed temporary GML file: {file_path}")
    except OSError as e:
        logging.error(f"Error removing temporary file {file_path}: {e}")

@pytest.fixture(scope="session") # Parse only once per session
def parsed_graph(gml_file_path):
    """Fixture to parse the GML file using the path from gml_file_path fixture."""
    try:
        graph = parse_shadow_gml(gml_file_path)
        return graph
    except Exception as e:
        pytest.fail(f"Setup failed: Could not parse GML file {gml_file_path}. Error: {e}")


# --- Test Functions ---

def test_graph_type_and_basic_properties(parsed_graph):
    """Verify graph type, directedness, node count, and edge count."""
    assert isinstance(parsed_graph, nx.DiGraph), "Parsed graph should be a NetworkX DiGraph"
    assert parsed_graph.is_directed(), "Graph should be directed"
    assert parsed_graph.number_of_nodes() == 3, "Incorrect number of nodes"
    assert parsed_graph.number_of_edges() == 4, "Incorrect number of edges"
    # Check graph-level attributes (optional)
    # assert parsed_graph.graph.get('id') == 'ExampleNet', "Graph ID attribute mismatch"
    # assert parsed_graph.graph.get('label') == 'A small test network for Shadow parsing', "Graph label attribute mismatch"

def test_node_existence_and_ids(parsed_graph):
    """Verify that all expected nodes exist with the correct IDs."""
    expected_node_ids = {0, 1, 2}
    assert set(parsed_graph.nodes()) == expected_node_ids, "Node IDs do not match expected set"

def test_node_attributes(parsed_graph):
    """Verify attributes for each node."""
    # Node 0 (HostA)
    assert 0 in parsed_graph.nodes
    node0_attrs = parsed_graph.nodes[0]
    assert node0_attrs.get('label') == "HostA"
    assert node0_attrs.get('asn') == 100
    assert isinstance(node0_attrs.get('asn'), int)
    assert node0_attrs.get('ip_addr') == "10.0.0.1"
    assert node0_attrs.get('host_bandwidth_up') == 100000000
    assert isinstance(node0_attrs.get('host_bandwidth_up'), int)
    assert node0_attrs.get('host_bandwidth_down') == 100000000
    assert isinstance(node0_attrs.get('host_bandwidth_down'), int)

    # Node 1 (Router1)
    assert 1 in parsed_graph.nodes
    node1_attrs = parsed_graph.nodes[1]
    assert node1_attrs.get('label') == "Router1"
    assert node1_attrs.get('asn') == 200
    assert isinstance(node1_attrs.get('asn'), int)
    # Check that attributes not present in GML are not added
    assert 'ip_addr' not in node1_attrs
    assert 'host_bandwidth_up' not in node1_attrs
    assert 'host_bandwidth_down' not in node1_attrs

    # Node 2 (HostB)
    assert 2 in parsed_graph.nodes
    node2_attrs = parsed_graph.nodes[2]
    assert node2_attrs.get('label') == "HostB"
    assert node2_attrs.get('asn') == 100
    assert isinstance(node2_attrs.get('asn'), int)
    assert node2_attrs.get('ip_addr') == "10.0.0.2"
    assert node2_attrs.get('host_bandwidth_up') == 50000000
    assert isinstance(node2_attrs.get('host_bandwidth_up'), int)
    assert node2_attrs.get('host_bandwidth_down') == 100000000
    assert isinstance(node2_attrs.get('host_bandwidth_down'), int)

def test_edge_existence(parsed_graph):
    """Verify that all expected directed edges exist."""
    expected_edges = [(0, 1), (1, 0), (1, 2), (2, 1)]
    for u, v in expected_edges:
        assert parsed_graph.has_edge(u, v), f"Edge {u}->{v} missing"

def test_edge_attributes(parsed_graph):
    """Verify attributes for each edge."""
    # Using pytest.approx for float comparisons
    # Edge 0 -> 1
    edge01_attrs = parsed_graph.edges[0, 1]
    assert edge01_attrs.get('label') == "Link_HostA_to_Router1"
    assert edge01_attrs.get('latency') == pytest.approx(10.5)
    assert isinstance(edge01_attrs.get('latency'), float)
    assert edge01_attrs.get('jitter') == pytest.approx(1.2)
    assert isinstance(edge01_attrs.get('jitter'), float)
    assert edge01_attrs.get('packet_loss') == pytest.approx(0.01)
    assert isinstance(edge01_attrs.get('packet_loss'), float)

    # Edge 1 -> 0
    edge10_attrs = parsed_graph.edges[1, 0]
    assert edge10_attrs.get('label') == "Link_Router1_to_HostA"
    assert edge10_attrs.get('latency') == pytest.approx(10.5)
    assert isinstance(edge10_attrs.get('latency'), float)
    assert edge10_attrs.get('jitter') == pytest.approx(0.0) # Check specified 0
    assert isinstance(edge10_attrs.get('jitter'), float)
    assert edge10_attrs.get('packet_loss') == pytest.approx(0.0) # Check specified 0
    assert isinstance(edge10_attrs.get('packet_loss'), float)

    # Edge 1 -> 2
    edge12_attrs = parsed_graph.edges[1, 2]
    assert edge12_attrs.get('label') == "Link_Router1_to_HostB"
    assert edge12_attrs.get('latency') == pytest.approx(15.0)
    assert isinstance(edge12_attrs.get('latency'), float)
    assert edge12_attrs.get('jitter') == pytest.approx(2.0)
    assert isinstance(edge12_attrs.get('jitter'), float)
    assert edge12_attrs.get('packet_loss') == pytest.approx(0.005)
    assert isinstance(edge12_attrs.get('packet_loss'), float)

    # Edge 2 -> 1
    edge21_attrs = parsed_graph.edges[2, 1]
    assert edge21_attrs.get('label') == "Link_HostB_to_Router1"
    assert edge21_attrs.get('latency') == pytest.approx(15.0)
    assert isinstance(edge21_attrs.get('latency'), float)
    assert edge21_attrs.get('jitter') == pytest.approx(1.8)
    assert isinstance(edge21_attrs.get('jitter'), float)
    assert edge21_attrs.get('packet_loss') == pytest.approx(0.008)
    assert isinstance(edge21_attrs.get('packet_loss'), float)

def test_file_not_found_error():
    """Test that FileNotFoundError is raised for non-existent files."""
    non_existent_path = "this_file_really_should_not_exist.gml"
    # Ensure the file really doesn't exist before testing
    if os.path.exists(non_existent_path):
         os.remove(non_existent_path) # Clean up just in case
    with pytest.raises(FileNotFoundError):
        parse_shadow_gml(non_existent_path)

def test_malformed_gml_error():
    """Test that NetworkXError (or potentially others) is raised for malformed GML."""
    # Example of malformed GML (missing closing brackets)
    malformed_gml = "graph [ directed 1 node [ id 0 "

    # Create a temporary file with malformed content
    # Use a different temp file for this specific test
    temp_f = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.gml', encoding='utf-8')
    temp_f.write(malformed_gml)
    temp_f.close()
    malformed_path = temp_f.name

    # Expecting NetworkXError, but catch base Exception to be safe
    with pytest.raises((nx.NetworkXError, Exception)):
         parse_shadow_gml(malformed_path)

    # Clean up the temporary file used for this test
    os.remove(malformed_path)

# --- Test Function for get_edge_delays_by_label ---

def test_get_edge_delays_by_label(parsed_graph):
    """Verify the get_edge_delays_by_label function."""
    edge_delays = get_edge_delays_by_label(parsed_graph)

    # Expected delays based on the TEST_GML_CONTENT and node labels
    # Only edges with valid source label, target label, and numeric latency included
    expected_delays = {
        ("HostA", "Router1"): 10.5,
        ("Router1", "HostA"): 10.5,
        ("Router1", "HostB"): 15.0,
        ("HostB", "Router1"): 15.0,
        # Edge 0->2 (HostA->HostB) skipped: missing latency
        # Edge 1->3 (Router1->?) skipped: target node 3 missing label
        # Edge 2->0 (HostB->HostA) skipped: non-numeric latency "invalid"
    }

    assert isinstance(edge_delays, dict), "Return type should be a dictionary"
    assert len(edge_delays) == len(expected_delays), \
        f"Expected {len(expected_delays)} entries in edge_delays, but got {len(edge_delays)}"

    # Check if all expected keys are present and values match (using approx for floats)
    for key, expected_value in expected_delays.items():
        assert key in edge_delays, f"Expected key '{key}' not found in edge_delays"
        assert edge_delays[key] == pytest.approx(expected_value), \
            f"Latency mismatch for key '{key}'. Expected {expected_value}, Got {edge_delays[key]}"

    # Check that no unexpected keys are present
    for key in edge_delays:
        assert key in expected_delays, f"Unexpected key '{key}' found in edge_delays"

def test_get_edge_delays_by_label_invalid_input():
    """Test get_edge_delays_by_label with invalid input type."""
    # Test with something that isn't a DiGraph
    with pytest.raises(TypeError):
        get_edge_delays_by_label("not a graph")
    with pytest.raises(TypeError):
        get_edge_delays_by_label(nx.Graph()) # Undirected graph
