#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
import logging
import os
import sys
from pathlib import Path

import argcomplete
import argparse

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
    
    argcomplete.autocomplete(parser)
    return parser

def main():
    """Maude HCS CLI

    Run 'maude-hcs --help' for command line usage information.

    """
    parser = build_cli_parser()
    args = parser.parse_args()
    init_logging(args.verbose)    


if __name__ == "__main__":
    main()
