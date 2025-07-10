import json
from pathlib import Path
import subprocess
import time
import itertools
from datetime import datetime
import sys
import os
import matplotlib.pyplot as plt

TOPLEVELDIR = Path(os.path.dirname(__file__))

# maude-hcs --verbose --shadow-filename=$SIM_FULL_FILENAME --model=prob --protocol=dns --filename=$GENERATED_FILENAME generate
# maude-hcs --verbose scheck --delta $DELTA --test ./results/$GENERATED_FILENAME.maude --query ./smc/$quatex_command.quatex -j 0
def smc(shadow_file:Path, generated_test_path:Path, smc_path:Path):
        subprocess.run(["maude-hcs", "--protocol=dns", "--shadow-filename=" + str(shadow_file.resolve()), "--model=prob", "--filename=" + str(generated_test_path.resolve()), "generate"], stdout=subprocess.DEVNULL)
        start = time.perf_counter()
        result = {}
        queries = {
             'latency.quatex': 0.5,
             'throughput.quatex': 150,
             'goodput.quatex': 150
        }
        for query, delta in queries.items():
            scheck_output = subprocess.run(["maude-hcs", "scheck", "--test=" + str(generated_test_path.resolve()), f"--query={str(Path.joinpath(smc_path, query).resolve())}", "--format", "json", "-j", "0", f"-d{str(delta)}"], capture_output=True, text=True, check=True)
            end = time.perf_counter()
            print(f"time: {end - start:.2f} seconds")
            new_result = json.loads(scheck_output.stdout)
            T = end - start
            result[query] = {}
            result[query]['smc'] = new_result
            result[query]['time'] = T

        return result


def main():    
    args = sys.argv
    if len(args) != 3:
         print(f'Expecting two arguments (1) the path of the directory with shadow files, and (2) path of results directory')
         sys.exit(1)
    use_case_path = TOPLEVELDIR.joinpath(sys.argv[1])
    result_path = TOPLEVELDIR.joinpath(sys.argv[2])
    smc_path = TOPLEVELDIR.parent.joinpath('smc')
    print(result_path)
    if not os.path.exists(result_path):
        os.mkdir(result_path)
    print(f'Loading shadow configs from {use_case_path}')
    files = sorted(list(filter(lambda x: x.endswith('yaml'), os.listdir(use_case_path))))
    for file in files:
        path = Path(os.path.join(use_case_path, file))
        print(f'Processing {path.resolve()}')
        result = smc(path, Path.joinpath(result_path, f'{path.stem}'), smc_path)
        result_file = result_path.joinpath(f'{path.stem}.json')
        print(f'Writing result to {str(result_file.resolve())}')
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)

         

if __name__ == "__main__":
    main()