import sys
import subprocess
from pathlib import Path

HOME_DIR = Path.home()
PWND_CP3_DIR = HOME_DIR / "Documents" / "pwnd2" / "pwnd-cp3"
PWND_CP2_DIR = HOME_DIR / "Documents" / "pwnd2" / "pwnd-cp2"
MAUDE_HCS_DIR = HOME_DIR / "Documents" / "pwnd2" / "maude-hcs"
CONFIG_FILE = PWND_CP3_DIR / "src" / "cp3_config.yaml"
OUTPUT_DIR = MAUDE_HCS_DIR / "scripts" / "gen_cp3" / "output"
MASTODON_ACTIONS_DIR = PWND_CP3_DIR / "src" / "static" / "mastodon_actions"
SKYHOOK_ACTIONS_DIR = PWND_CP3_DIR / "src" / "static" / "skyhook_actions"

def gen_markov(json_dir, out_dir):
    """Generate action files from all json files in json_dir"""

    subprocess.run([
        "maude-hcs", "--verbose",
        "markov",
        "--protocol=mastodon",
        f"--json-dir={json_dir}",
        f"--maude-dir={out_dir}",
    ])

def gen_config(cfg_file, out_dir, out_name):
    """Produce maude initial state file from yaml cfg_file"""

    subprocess.run([
        "maude-hcs", "--verbose", 
        "generate",
        "--model=prob",
        "--parse-type=cp2",
        f"--yml-filename={cfg_file}",
        f"--output-dir={out_dir}",
        "--filename=out",
    ])

def main():
    # gen_markov(MASTODON_ACTIONS_DIR, OUTPUT_DIR)
    # gen_config(CONFIG_FILE, OUTPUT_DIR, "out")
    gen_config(HOME_DIR / "Documents" / "pwnd_cp3_spot_check_1.yaml", OUTPUT_DIR, "out")

    # For testing old (cp2) generation
    # gen_config(
    #     PWND_CP2_DIR / "cp2_scenarios" / "cp2_scenario_1" / "cp2_scenario_1.yml",
    #     OUTPUT_DIR, "out"
    # )

if __name__ == "__main__":
    main()