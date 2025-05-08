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

from .common import save_output
from maude_hcs.analysis import HCSAnalysis
from maude_hcs.parsers.graph import parse_shadow_gml, get_node_names, get_edge_delays_by_label, get_edge_info_by_label
import logging
import json

from umaudemc.command.scheck import scheck
import importlib.util
import maude

logger = logging.getLogger(__name__)

GENERATE_NAME = 'generate'
SCHECK_NAME = 'scheck'

def handle_command(command, parser, args):
    handlers = {
        GENERATE_NAME: handle_generate,
<<<<<<< HEAD
        SCHECK_NAME: handle_scheck
=======
				SCHECK_NAME: handle_scheck
>>>>>>> 4246dc3 (maude-hcs scheck command)
    }

    if command in handlers:
        handlers[command](args, parser)

    else:
        parser.error("Unknown command: {}".format(command))

def handle_generate(args, parser):
    logger.debug("Handle maude generation")
    run_args = json.load(args.run_args)
    run_args["topology"] = {}
    if args.topology_filename:
      topology_graph  = parse_shadow_gml(args.topology_filename)
      run_args["topology"] = {
          "node_names": get_node_names(topology_graph),
          "edges_delay": get_edge_delays_by_label(topology_graph),
          "edges_info": get_edge_info_by_label(topology_graph)
      }
    result = HCSAnalysis(args, run_args).generate()
    filename = args.filename
    if filename == None:
        filename = f'generated_{run_args.get("name", "unknown")}_{args.model}'
    save_output(parser, run_args, result, filename)

def handle_scheck(args, parser):
    logger.debug("Handle umaudemc scheck")

    has_umaudemc = importlib.util.find_spec('umaudemc')
    if not has_umaudemc:
                    logger.error('The umaudemc Python package is not available. It can be installed with "pip install umaudemc".')
    maude.init(advise=args.advise)
    maude.load(args.test)	
    result = scheck(args)
