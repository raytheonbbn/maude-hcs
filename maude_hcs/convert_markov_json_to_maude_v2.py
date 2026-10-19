import logging
import os
import sys

from maude_hcs.lib import GLOBALS
from maude_hcs.parsers.markovV2JsonToMaudeParser import HEADER, JsonToMaudeV2Parser

logger = logging.getLogger(__name__)
LOAD_PATH = (GLOBALS.LIB_DIR / "common" / "maude" / "markov-action-model-v2.maude").resolve()


class MarkovJsonToMaudeConverter(JsonToMaudeV2Parser):
    """Use the shared v2 converter with the CLI's absolute library path.

    Keeping conversion in one implementation ensures builds and direct parser
    users apply the same user-model timing defaults.
    """

    def __init__(self, model_name, stem, load_path=LOAD_PATH):
        super().__init__(model_name, stem, load_path)


def process_directories(args, input_root, output_root):
    """
    Recursively finds all .json files in input_root, converts them to Maude v2,
    and writes them to the same relative path in output_root.
    """
    if not os.path.exists(input_root):
        logger.error(f"Error: Input directory '{input_root}' does not exist.")
        return

    logger.debug(f"Starting v2 conversion from '{input_root}' to '{output_root}'...")

    count = 0
    for root, dirs, files in os.walk(input_root):
        for file in files:
            if file.endswith(".json"):
                full_input_path = os.path.join(root, file)
                rel_dir = os.path.relpath(root, input_root)
                stem = os.path.splitext(file)[0]
                proto = args.protocol
                if "tgen_user_models" in full_input_path and not proto.endswith("tgen"):
                    stem_clean = f"{proto}-tgen-{stem.replace('_', '-')}"
                else:
                    stem_clean = f"{proto}-{stem.replace('_', '-')}"

                target_dir = os.path.join(output_root, rel_dir)
                os.makedirs(target_dir, exist_ok=True)

                output_filename = f"{stem}.maude"
                full_output_path = os.path.join(target_dir, output_filename)

                try:
                    with open(full_input_path, 'r') as f:
                        json_content = f.read()

                    parser = MarkovJsonToMaudeConverter(
                        model_name=stem_clean,
                        stem=stem,
                    )
                    maude_content = parser.generate(json_content)

                    with open(full_output_path, 'w') as f:
                        f.write(maude_content)

                    logger.debug(f"Generated: {full_output_path}")
                    count += 1

                except Exception as e:
                    logger.error(f"Error processing {full_input_path}: {e}")
                    import traceback
                    traceback.print_exc()

    logger.info(f"Done. Processed {count} files.")


def convert_single_file(args):
    """Convert a single JSON file to Maude v2 format."""
    input_path = args.input_file
    output_path = args.output_file

    if not os.path.exists(input_path):
        logger.error(f"Error: Input file '{input_path}' does not exist.")
        return

    stem = os.path.splitext(os.path.basename(input_path))[0]
    proto = args.protocol
    if "tgen_user_models" in os.path.abspath(input_path) and not proto.endswith("tgen"):
        stem_clean = f"{proto}-tgen-{stem.replace('_', '-')}"
    else:
        stem_clean = f"{proto}-{stem.replace('_', '-')}"

    if output_path is None:
        output_dir = os.path.dirname(input_path)
        output_path = os.path.join(output_dir, f"{stem}.maude")

    with open(input_path, 'r') as f:
        json_content = f.read()

    parser = MarkovJsonToMaudeConverter(
        model_name=stem_clean,
        stem=stem,
    )
    maude_content = parser.generate(json_content)

    with open(output_path, 'w') as f:
        f.write(maude_content)

    logger.info(f"Generated: {output_path}")


def convert(args):
    logging.basicConfig(level=logging.DEBUG)

    if args.markov_command == "batch":
        process_directories(args, args.input_dir, args.output_dir)
    elif args.markov_command == "single":
        convert_single_file(args)
    else:
        print("Usage: maude-hcs markov {batch,single} ...")
        sys.exit(1)