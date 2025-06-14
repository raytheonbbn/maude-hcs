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

def add_initial_data_args(parser):
  """Arguments for the basic input data of a model-checking problem"""

  parser.add_argument(
    '-m', '--module',
    help='specify the module for model checking',
    metavar='NAME'
  )

  parser.add_argument(
    '-M', '--metamodule',
    help='specify a metamodule for model checking',
    metavar='TERM'
  )
  parser.add_argument(
    '--opaque',
    help='opaque strategy names (comma-separated)',
    metavar='LIST',
    default=''
  )
  parser.add_argument(
    '--full-matchrew',
    help='enable full matchrew trace generation',
    action='store_true'
  )
  parser.add_argument(
    '--purge-fails',
    help='remove states where the strategy has failed from the model',
    choices=['default', 'yes', 'no'],
    default='default'
  )
  parser.add_argument(
    '--merge-states',
    help='avoid artificial branching due to strategies by merging states',
    choices=['default', 'state', 'edge', 'no'],
    default='default'
  )

def build_cli_parser():
    parser = argparse.ArgumentParser("maude-hcs")
    parser.add_argument('--verbose', action='store_true', help='turn on logging')    
    parser.add_argument('--run-args-file', dest='run_args', type=lambda x: is_valid_file(parser, x),
                        metavar='FILE', required=False, help=f'File containing all of the run arguments')
    parser.add_argument("--shadow-filename",
        dest="shadow_filename",        
        type=lambda x: is_valid_file(parser, x),
        metavar='FILE',
        default=None,
        help="Name of the shadow yaml config file, which includes the topology gml file path and other params",
        required=False)
    parser.add_argument('--filename', dest='filename', type=str, required=False, default=None, help=f'Name of output file')
    parser.add_argument('--model', dest='model', required=False, 
            choices=GLOBALS.MODEL_TYPES,
            default=GLOBALS.MODEL_TYPES[0],
            help=f'Choose one of the following options: {", ".join(GLOBALS.MODEL_TYPES)}. Default is {GLOBALS.MODEL_TYPES[0]}.'
    )

    cmd_parser = parser.add_subparsers(title='command', dest='command')    
    cmd_parser.required = True
    generate_parser = cmd_parser.add_parser('generate')

    parser_scheck = cmd_parser.add_parser('scheck')

    parser_scheck.add_argument(
        '--advise',
        help='do not suppress debug messages from Maude',
        dest='advise',
        action='store_true'
    )
    parser_scheck.add_argument('--protocol', dest='protocol', required=False, 
            choices=GLOBALS.MODULES,
            default=GLOBALS.MODULES[0],
            help=f'Choose one of the following options: {", ".join(GLOBALS.MODULES)}. Default is {GLOBALS.MODULES[0]}.'
    )
    parser_scheck.add_argument('--file', help='Maude source file specifying the model-checking problem', required=False)
    parser_scheck.add_argument('--test', help='maude-hcs generated test, default=results/generated_test.maude', default='results/generated_test.maude')
    parser_scheck.add_argument('--initial', help='initial term, default=initConfig', default='initConfig')
    parser_scheck.add_argument('--query', help='QuaTEx query, default=smc/query.quatex', default='smc/query.quatex')
    parser_scheck.add_argument('strategy', help='strategy expression', nargs='?')

    add_initial_data_args(parser_scheck)

    parser_scheck.add_argument(
        '--assign',
        help='Assign probabilities to the successors according to the given method, default=pmaude',
        metavar='METHOD',
        default='pmaude'
    )
    parser_scheck.add_argument(
        '--alpha', '-a',
        help='Complement of the confidence level (probability outside the confidence interval), default=0.05',
        type=float,
        default=0.05
    )
    parser_scheck.add_argument(
        '--delta', '-d',
        help='Maximum admissible radius for the confidence interval, default=0.5',
        type=float,
        default=0.5
    )
    parser_scheck.add_argument(
        '--block', '-b',
        help='Number of simulations before checking the confidence interval, default=30',
        type=int,
        default=30
    )
    parser_scheck.add_argument(
        '--nsims', '-n',
        help='Number of simulations (it can be a fixed number or a range min-max, where any of the limits can be omitted), default=30-',
        default='30-'
    )
    parser_scheck.add_argument(
        '--seed', '-s',
        help='Random seed',
        type=int
    )
    parser_scheck.add_argument(
        '--jobs', '-j',
        help='Number of parallel simulation threads, default=1',
        type=int,
        default=1
    )
    parser_scheck.add_argument(
        '--format', '-f',
        help='Output format for the simulation results, default=text',
        choices=['text', 'json'],
        default='text'
    )
    parser_scheck.add_argument(
        '--plot', '-p',
        help='Plot the results of parametric queries (using Matplotlib)',
        action='store_true'
    )
    
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
