from maude_hcs.serialize import MaudeHCSEncoder
import logging
import sys
import os
from pathlib import Path

logger = logging.getLogger(__name__)

TOPLEVELDIR = Path(os.path.dirname(__file__))

def _legalize_name(name):
    name = name.replace('(', '.')
    name = name.replace('=', '')
    name = name.replace(',', '.')
    name = name.replace(')', '')
    return name

def name_object(name, ending='json'):
    return f'{_legalize_name(name)}.{ending}'

def save_output(parser, args, target, filename):
    output_args = args.get('output')
    if output_args.get('save_output'):
        output_dir = os.path.join('.', output_args.get('directory'))
        logger.debug(output_dir)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        format = output_args.get('result_format')

        handle_write_to_directory(parser, output_dir, output_args.get('force_save'),
                                  lambda: MaudeHCSEncoder(format).encode(target),
                                  name_object(filename, format))

def handle_write_to_directory(parser, output_dir, force, get_contents, preferred_file_name):
    output_file = os.path.join(output_dir, preferred_file_name)
    if os.path.exists(output_file):
        if os.path.isdir(output_file):
            parser.error(f'error: output path is a directory', file=sys.stderr)
        if force:
            print(f'Overwriting {output_file}')
        else:
            parser.error(f'file already exists, use -f/--force to overwrite {output_file}', file=sys.stderr)

    with open(output_file, 'w') as f:
        f.write(get_contents())

    logger.info(f'Wrote to {output_file}')

    return True        