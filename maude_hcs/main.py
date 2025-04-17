#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
import logging
import os
import sys

from pathlib import Path

import argcomplete
import argparse
from maude_hcs.cli import handle_command, MODEL_TYPES

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
    parser.add_argument('--model', dest='model', required=False, 
            choices=MODEL_TYPES,
            default=MODEL_TYPES[0],
            help=f'Choose one of the following options: {", ".join(MODEL_TYPES)}. Default is {MODEL_TYPES[0]}.'
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
