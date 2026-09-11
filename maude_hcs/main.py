#!/usr/bin/env python
# MAUDE_HCS: maude_hcs
#
# Software Markings (UNCLASS)
# Maude-HCS Software
#
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
#
# The computer software and computer software documentation are licensed
# under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. A copy of the License
# is provided in the LICENSE file, but you may obtain a copy of the
# License at:  https://www.apache.org/licenses/LICENSE-2.0
#
# The computer software and computer software documentation are based
# upon work supported by the Defense Advanced Research Projects Agency (DARPA)
# under Agreement No. HR00l 12590083.
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
# contained herein. Refer to the provided NOTICE file.
#
# MAUDE_HCS: end

# PYTHON_ARGCOMPLETE_OK
import logging
import os
import sys

from pathlib import Path

import argcomplete
import argparse
from maude_hcs.lib import GLOBALS
from .generate_cp3 import generate
from .convert_markov_json_to_maude import convert

from umaudemc.command.scheck import scheck
import importlib.util
import maude

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

# def add_initial_data_args(parser):
#   """Arguments for the basic input data of a model-checking problem"""

#   parser.add_argument(
#     '-m', '--module',
#     help='specify the module for model checking',
#     metavar='NAME'
#   )

#   parser.add_argument(
#     '-M', '--metamodule',
#     help='specify a metamodule for model checking',
#     metavar='TERM'
#   )
#   parser.add_argument(
#     '--opaque',
#     help='opaque strategy names (comma-separated)',
#     metavar='LIST',
#     default=''
#   )
#   parser.add_argument(
#     '--full-matchrew',
#     help='enable full matchrew trace generation',
#     action='store_true'
#   )
#   parser.add_argument(
#     '--purge-fails',
#     help='remove states where the strategy has failed from the model',
#     choices=['default', 'yes', 'no'],
#     default='default'
#   )
#   parser.add_argument(
#     '--merge-states',
#     help='avoid artificial branching due to strategies by merging states',
#     choices=['default', 'state', 'edge', 'no'],
#     default='default'
#   )

def build_cli_parser():
    parser = argparse.ArgumentParser("maude-hcs")
    parser.add_argument('--verbose', action='store_true', help='turn on logging')

    cmd_subparsers = parser.add_subparsers(title="command", dest="command")
    cmd_subparsers.required = True

    # Maude generation command
    generate_parser = cmd_subparsers.add_parser('generate')

    generate_parser.add_argument("yaml_file", help="Path to scenario YAML")
    generate_parser.add_argument("--baselineTime", type=float, default=None, help="Duration of baseline run")
    generate_parser.add_argument("--runTime", type=float, default=None, help="Duration of actual run")
    generate_parser.add_argument("--hcsDelay", type=float, default=10.0, help="When to start hcs")
    generate_parser.add_argument("--tgenDelay", type=float, default=1.0, help="When to start tgens")
    generate_parser.add_argument("--outDir", default=None, help="Output directory for generated Maude files (default: directory of YAML file)")
    generate_parser.add_argument("--scenarioName", default=None, help="Scenario name for generated Maude files (default: basename of YAML without extension)")
    generate_parser.add_argument("--parallelizeBaseline", action="store_true", help="If set, generate separate baseline files per feature and vantage point in a 'baselines' directory")
    generate_parser.add_argument("--quatex", action="store_true", help="generate quatex file for combinations?")
    generate_parser.add_argument("--perf", action="store_true", help="Performance mode: removes baseLineAct and sets Adversary useTcpTPL to false")    
    generate_parser.add_argument("--confidentiality", action="store_true", help="Confidentiality mode: only quatex needed for computing confidentiality")    
    generate_parser.add_argument("--notgens", action="store_true", help="disable tgens firing")

    combo_group = generate_parser.add_mutually_exclusive_group()
    combo_group.add_argument("--filterVpFeatCombos", action="store_true", help="filter the combinations of VP and feature")
    combo_group.add_argument("--filterVpFeatCombos2", action="store_true", help="filter the combinations of VP and feature (different vps)")
    combo_group.add_argument(
        "--filterVpFeatCombo4x5",
        action="store_true",
        help="use the combo4x5 set of four vantage points and five features",
    )
    combo_group.add_argument(
        "--filterVpFeatTop25",
        action="store_true",
        help="use the Top 25 vantage-point and feature sets",
    )
    combo_group.add_argument(
        "--filterVpFeatIxp",
        action="store_true",
        help="use ixpN as the only vantage point and retain all features",
    )

    # Markov generation subcommands
    markov_parser = cmd_subparsers.add_parser('markov')
    markov_subparsers = markov_parser.add_subparsers(title="markov command", dest="markov_command")

    # Batch mode (directory)
    batch_parser = markov_subparsers.add_parser("batch", help="Batch convert a directory of JSON files.")
    batch_parser.add_argument("protocol", help="The protocol name, for naming purposes.")
    batch_parser.add_argument("input_dir", help="The input directory containing JSON files.")
    batch_parser.add_argument("output_dir", help="The output directory for Maude files.")

    # Single file mode
    single_parser = markov_subparsers.add_parser("single", help="Convert a single JSON file.")
    single_parser.add_argument("protocol", help="The protocol name, for naming purposes.")
    single_parser.add_argument("input_file", help="The input JSON file.")
    single_parser.add_argument("output_file", nargs="?", default=None,
                               help="The output Maude file (default: same dir as input, with -v2.maude extension).")

    # scheck command to run SMC
    scheck_parser = cmd_subparsers.add_parser('scheck')
    scheck_parser.add_argument(
        '--advise',
        help='do not suppress debug messages from Maude',
        dest='advise',
        action='store_true'
    )
    scheck_parser.add_argument('--file', help='Maude source file specifying the model-checking problem', required=False)
    scheck_parser.add_argument('--test', help='maude-hcs generated test, default=results/generated_test.maude', default='results/generated_test.maude')
    scheck_parser.add_argument('--initial', help='initial term, default=initConfig', default='initConfig')
    scheck_parser.add_argument('--query', help='QuaTEx query, default=smc/query.quatex', default='smc/query.quatex')
    scheck_parser.add_argument('strategy', help='strategy expression', nargs='?')

    # add_initial_data_args(parser_scheck)

    # parser_scheck.add_argument(
    #     '--assign',
    #     help='Assign probabilities to the successors according to the given method, default=pmaude',
    #     metavar='METHOD',
    #     default='pmaude'
    # )
    # parser_scheck.add_argument(
    #     '--alpha', '-a',
    #     help='Complement of the confidence level (probability outside the confidence interval), default=0.05',
    #     type=float,
    #     default=0.05
    # )
    # parser_scheck.add_argument(
    #     '--delta', '-d',
    #     help='Maximum admissible radius for the confidence interval, default=0.5',
    #     type=float,
    #     default=0.5
    # )
    # parser_scheck.add_argument(
    #     '--block', '-b',
    #     help='Number of simulations before checking the confidence interval, default=30',
    #     type=int,
    #     default=30
    # )

    scheck_parser.add_argument(
        '--nsims', '-n',
        help='Number of simulations (it can be a fixed number or a range min-max, where any of the limits can be omitted), default=30-',
        default='30-'
    )
    scheck_parser.add_argument(
        '--seed', '-s',
        help='Random seed',
        type=int
    )
    scheck_parser.add_argument(
        '--jobs', '-j',
        help='Number of parallel simulation threads, default=1',
        type=int,
        default=1
    )
    scheck_parser.add_argument(
      '--distribute',
      help='Distribute the computation over some machines'
    )
    scheck_parser.add_argument(
      '-D',
      action='append',
      help='Define a constant to be used in QuaTEx expressions'
    )
    scheck_parser.add_argument(
      '--dump',
      help='Dump query evaluations into the given file',
    )
    scheck_parser.add_argument(
        '--format', '-f',
        help='Output format for the simulation results, default=text',
        choices=['text', 'json'],
        default='text'
    )
    scheck_parser.add_argument(
        '--plot', '-p',
        help='Plot the results of parametric queries (using Matplotlib)',
        action='store_true'
    )
    
    argcomplete.autocomplete(generate_parser)
    return generate_parser

def handle_command(command, parser, args: argparse.Namespace):
    match command:
        case "generate":
            generate(args)
        case "scheck":
            handle_scheck(args)
        case "markov":
            print(vars(args))
            convert(args)
        case _:
            if parser is not None:
                parser.error(f"Unknown command: {command}")

def handle_scheck(args):
    logger.debug("Handle umaudemc scheck")

    if not args.file:        
        args.file = str(GLOBALS.TOP_LEVEL_DIR.joinpath(Path(f"maude_hcs/lib/smc/smc.maude")))
    logger.debug(f"Loaded SMC file {args.file}")

    has_umaudemc = importlib.util.find_spec('umaudemc')
    if not has_umaudemc:
        logger.error('The umaudemc Python package is not available. It can be installed with "pip install umaudemc".')
    maude.init(advise=args.advise)
    maude.load(args.test)
    scheck(args)

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
