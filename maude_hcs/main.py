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

# PYTHON_ARGCOMPLETE_OK
import logging
import os
import sys

from pathlib import Path

import argcomplete
import argparse
from maude_hcs.cli import handle_command
from maude_hcs.lib import GLOBALS

from Maude.attack_exploration.src.zone import Record

TOPLEVELDIR = Path(os.path.dirname(__file__))

logger = logging.getLogger(__name__)

def init_logging(verbose):
    _logger = logging.getLogger('maude-hcs')
    if verbose:
        _logger.setLevel(logging.DEBUG)
    else:
        _logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("{levelname} : {message}", style='{')
    handler.setFormatter(formatter)
    _logger.addHandler(handler)


def is_valid_file(parser, arg):
    if not os.path.exists(arg):
        parser.error("The file {} does not exist".format(arg))
    else:
        return open(arg, 'r')


def build_cli_parser():
    parser = argparse.ArgumentParser("maude-hcs")
    parser.add_argument('--verbose', action='store_true', help='turn on logging')    
    parser.add_argument('--run-args-file', dest='run_args', type=lambda x: is_valid_file(parser, x),
                        metavar='FILE', required=False, help=f'File containing all of the run arguments')
    parser.add_argument('--filename', dest='filename', type=str, required=False, default=None, help=f'Name of output file')
    parser.add_argument('--model', dest='model', required=False, 
            choices=GLOBALS.MODEL_TYPES,
            default=GLOBALS.MODEL_TYPES[0],
            help=f'Choose one of the following options: {", ".join(GLOBALS.MODEL_TYPES)}. Default is {GLOBALS.MODEL_TYPES[0]}.'
)

    cmd_parser = parser.add_subparsers(title='command', dest='command')    
    cmd_parser.required = True
    generate_parser = cmd_parser.add_parser('generate')
    # generator = generate_parser.add_subparsers(title='generator', dest='generator',
    #                                           description='Generate Maude file(s) to run', help="Add help")
    # generator.required = True
    # generator.add_parser('nondet', description='Generate non-deterministic model', help='nondet for nondeterministic')
    # generator.add_parser('prob', description='Generate probabilistic model', help='prob for probabilistic')
    
    argcomplete.autocomplete(parser)
    return parser

def main():
    """Maude HCS CLI

    Run 'maude-hcs --help' for command line usage information.

    """

    parser = build_cli_parser()
    args = parser.parse_args()
    init_logging(args.verbose)    
    
    handle_command(args.command, parser, args)


if __name__ == "__main__":
    main()
