from .common import save_output
from maude_hcs.analysis import HCSAnalysis
from maude_hcs.parsers.graph import parse_shadow_gml, get_node_names, get_edge_delays_by_label, get_edge_info_by_label
import logging
import json

logger = logging.getLogger(__name__)

GENERATE_NAME = 'generate'

def handle_command(command, parser, args):
    handlers = {
        GENERATE_NAME: handle_generate
    }

    if command in handlers:
        handlers[command](args, parser)

    else:
        parser.error("Unknown command: {}".format(command))

def handle_generate(args, parser):
    logger.debug("Handle maude generation")
    run_args = json.load(args.run_args)
    if not args.topology_filename is None:
      topology_graph  = parse_shadow_gml(args.topology_filename)
      run_args["topology"] = {
          "node_names": get_node_names(topology_graph),
          "edges_delay": get_edge_delays_by_label(topology_graph),
          "edges_info": get_edge_info_by_label(topology_graph)
      }
    else:
      run_args["topology"] = {
      }
    result = HCSAnalysis(args, run_args).generate()
    filename = args.filename
    if filename == None:
        filename = f'generated_{run_args.get("name", "unknown")}_{args.model}'
    save_output(parser, run_args, result, filename)


    

    
    
