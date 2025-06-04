import networkx as nx
import logging

logger = logging.getLogger(__name__)

def _simple_type_converter(value_str):
    """
    Attempts to convert GML string values read by networkx
    to int or float if possible.

    NetworkX's GML reader provides values *after* handling quotes.
    This function tries to infer the numeric type.

    Args:
        value_str: The attribute value (potentially string).

    Returns:
        The value converted to int, float, or the original type (likely string).
    """
    # Check if it's already a number (NetworkX might sometimes parse directly)
    if isinstance(value_str, (int, float)):
        return value_str
    # If it's a string, try converting
    if isinstance(value_str, str):
        try:
            # Try converting to integer first
            return int(value_str)
        except ValueError:
            try:
                # If int fails, try converting to float
                return float(value_str)
            except ValueError:
                # If both fail, return the original string
                return value_str
    # Return original value if not a string or number we handle
    return value_str

def parse_shadow_gml(gml_path: str) -> nx.DiGraph:
    """
    Parses a GML file specified according to Shadow's network graph format
    (https://shadow.github.io/docs/guide/network_graph_spec.html)
    and returns a NetworkX DiGraph object.

    Node and edge attributes specified in the GML are included in the graph.
    Numeric attributes are converted to int or float where possible.

    Args:
        gml_path: The path to the GML file.

    Returns:
        A NetworkX DiGraph object representing the network.

    Raises:
        FileNotFoundError: If the gml_path does not exist.
        nx.NetworkXError: If the GML file is malformed or cannot be parsed by NetworkX.
        TypeError: If the parsed graph is unexpectedly not directed.
        Exception: For other unexpected errors during parsing.
    """
    logging.info(f"Attempting to parse Shadow GML file: {gml_path}")
    try:
        # Use networkx's built-in GML reader:
        # - label='id': Use the 'id' attribute from GML as the node identifier in NetworkX.
        # - destringizer: Apply our function to convert attribute values from strings.
        graph = nx.read_gml(gml_path, label='id', destringizer=_simple_type_converter)

        # Verify that the graph is directed, as expected for Shadow networks
        # The 'directed 1' line in GML should ensure this, but we double-check.
        if not graph.is_directed():
            # This case should be rare if 'directed 1' is present and parsed correctly
            logging.warning(f"Parsed graph from {gml_path} was not directed. Attempting conversion.")
            # Convert the graph to a directed graph
            graph = nx.DiGraph(graph)
            if not graph.is_directed():
                 # If conversion fails, something is fundamentally wrong
                 raise TypeError(f"Could not ensure the graph from {gml_path} is directed.")

        convert_names_to_maude_names(graph)

        logging.info(f"Successfully parsed GML. Graph has {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges.")

        # Optional: Log details of a sample node and edge for debugging
        if graph.nodes:
            node_id_example = list(graph.nodes())[0]
            logging.debug(f"Sample Node (ID: {node_id_example}) Attributes: {graph.nodes[node_id_example]}")
        if graph.edges:
            edge_example = list(graph.edges())[0]
            logging.debug(f"Sample Edge {edge_example} Attributes: {graph.edges[edge_example]}")

        return graph

    except FileNotFoundError:
        logging.error(f"GML file not found at path: {gml_path}")
        raise # Re-raise the specific error
    except nx.NetworkXError as e:
        logging.error(f"NetworkX failed to parse GML file '{gml_path}': {e}")
        raise # Re-raise the specific error
    except Exception as e:
        logging.error(f"An unexpected error occurred during GML parsing of '{gml_path}': {e}")
        raise # Re-raise any other exceptions


def get_node_names(graph: nx.DiGraph) -> list:
  """
  Get the shadow node names.

  Args:
    graph: The graph from which to get the node names.

  Returns:
    A list of the shadow node names.
  """
  node_names  = [graph.nodes[id]["label"] for id in graph.nodes.keys()]
  return node_names


def convert_names_to_maude_names(graph: nx.DiGraph) -> nx.DiGraph:
  """
  Shadow names may include characters that are special in maude, including _.
  Change it to non offending characters.

  Args:
    graph: The graph whose node labels need to change.

  Returns:
    An updated graph.

  """
  for node_id in graph.nodes:
    node = graph.nodes[node_id]
    node["label"] = node.get("label").replace('_', '-')


def get_edge_info_by_label(graph: nx.DiGraph) -> dict:
  """
  Get edge info mapped to a link label.

  Args:
    graph: The graph from which to get that info.

  Returns:
    The dictionary of labels to edge information.
  """
  link_info = dict()
  for u_id, v_id, edge_data in graph.edges(data=True):
    source_node_data  = graph.nodes[u_id]
    target_node_data  = graph.nodes[v_id]

    source_label      = source_node_data.get("label")
    target_label      = target_node_data.get("label")
    latency_value     = parse_latency_str(edge_data.get("latency", "-1."))
    jitter_value      = parse_latency_str(edge_data.get("jitter", "0s"))
    loss_value        = parse_loss_str(edge_data.get("packet_loss", "0."))

    if source_label is None or target_label is None or latency_value == -1.:
      raise ValueError("Missing or malformatted information")
    else:
      link_info[f"{source_label}->{target_label}"] = {
          "latency": latency_value,
          "jitter": jitter_value,
          "loss": loss_value,
      }

  return link_info


def get_edge_delays_by_label(graph: nx.DiGraph) -> dict:
    """
    Extracts edge latencies from a parsed graph, using node labels for keys.

    Assumes nodes have a 'label' attribute and edges have a 'latency' attribute.
    Skips edges where either node label or edge latency is missing.

    Args:
        graph: A NetworkX DiGraph, presumably parsed from Shadow GML,
               containing node 'label' and edge 'latency' attributes.

    Returns:
        A dictionary where keys are strings "source_label->target_label"
        and values are the corresponding edge latencies (float).
    """
    if not isinstance(graph, nx.DiGraph):
        logging.error("Input graph is not a NetworkX DiGraph.")
        # Depending on requirements, could raise TypeError or return empty dict
        raise TypeError("Input must be a NetworkX DiGraph.")

    edge_delays = {}
    skipped_count = 0

    for u_id, v_id, edge_data in graph.edges(data=True):
        try:
            # Retrieve source and target node data
            source_node_data = graph.nodes[u_id]
            target_node_data = graph.nodes[v_id]

            # Get labels and latency using .get() to handle potential missing keys
            source_label = source_node_data.get('label')
            target_label = target_node_data.get('label')
            latency_str = edge_data.get('latency')

            # Check if all required attributes are present and latency is numeric
            if source_label is not None and target_label is not None and latency_str is not None:
                # Ensure latency is treated as a number (float likely)
                try:
                    numeric_latency = parse_latency_str(latency_str)
                    edge_key = (source_label, target_label)
                    edge_delays[edge_key] = numeric_latency
                except (ValueError, TypeError):
                     logging.warning(f"Edge ({u_id}->{v_id}) latency '{latency_str}' is not a valid number. Skipping.")
                     skipped_count += 1
            else:
                # Log which attribute was missing
                missing = []
                if source_label is None: missing.append(f"source label for node {u_id}")
                if target_label is None: missing.append(f"target label for node {v_id}")
                if latency_str is None: missing.append(f"latency for edge ({u_id}->{v_id})")
                logging.warning(f"Skipping edge ({u_id}->{v_id}) due to missing attributes: {', '.join(missing)}.")
                skipped_count += 1

        except KeyError as e:
            # This handles cases where u_id or v_id might somehow not be in graph.nodes
            logging.error(f"Node ID {e} not found while processing edge ({u_id}, {v_id}). Skipping edge.")
            skipped_count += 1
        except Exception as e:
            # Catch unexpected errors during processing of a single edge
            logging.error(f"Unexpected error processing edge ({u_id}->{v_id}): {e}. Skipping edge.")
            skipped_count += 1


    if skipped_count > 0:
        logging.info(f"Processed edges. Skipped {skipped_count} edge(s) due to missing labels or latency.")

    logging.info(f"Generated edge delay dictionary with {len(edge_delays)} entries.")
    return edge_delays


def parse_latency_str(latency_str: str) -> float:
  """
  Parse a latency string like "50ms".

  Args:
    latency_str: The latency string to parse.

  Returns:
    The numerical value in seconds.
  """
  unit_divisor  = 1
  if 'ms' in latency_str:
    unit_divisor = 1e3
  elif 'us' in latency_str:
    unit_divisor  = 1e6
  latency_str = latency_str.replace('ms','').replace('us','').replace('s','')
  try:
    numeric_latency = float(latency_str) / unit_divisor
  except ValueError as e:
    print(f"Latency {latency_str} is not a valid value")
    raise ValueError(e)
  return numeric_latency


def parse_loss_str(loss_str: str) -> float:
  """
  Parse a loss string like "0.1".

  Args:
    loss_str: The loss string to parse.

  Returns:
    The numerical valued.
  """
  try:
    numeric_loss = float(loss_str)
    return numeric_loss
  except ValueError as e:
    print(f"Loss {loss_str} is not a valid value")
    raise ValueError(e)


def find_node_name(nodes: list, substrings: list, default=None) -> list:
  """
  Find the node name that matches at least one element of a list of substrings.

  Args:
    nodes: The list of nodes with proper names, like "application-client", "tld-dns", etc..
    substrings: The list of abreviated names, like "client" or "tld".
    default: The default name to return if none is found to match in 'nodes'.
  """
  if nodes is None:
    return default

  node_names  = []
  for substring in substrings:
    node_names.extend(list(filter(lambda s: substring in s, nodes)))
  if len(node_names) > 1:
    print(f"Warning: more than one match for {substrings} in {nodes}.")
    raise ValueError
  if len(node_names) == 0:
    print(f"No testbed shadow file node corresponding to {substrings}.")
    if default is None:
      raise ValueError
    return default
  return node_names[0]
