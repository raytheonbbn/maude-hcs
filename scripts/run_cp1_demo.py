import json
from pathlib import Path
import subprocess
import time
import sys
import os

TOPLEVELDIR = Path(os.path.dirname(__file__))

def smc(shadow_file:Path, generated_test_path:Path, smc_path:Path):
        gen_cmd = ["maude-hcs", "--protocol=dns", "--shadow-filename=" + str(shadow_file.resolve()), "--model=prob", "--filename=" + str(generated_test_path.resolve()), "generate"]
        subprocess.run(gen_cmd, stdout=subprocess.DEVNULL)        
        result = {}
        queries = {
             'latency.quatex': 1,
             'throughput.quatex': 500,
             'goodput.quatex': 500
        }
        result['gen cmd'] = ' '.join([x for x in gen_cmd])
        print(f'{result['gen cmd']}')
        for query, delta in queries.items():
            result[query] = {}            
            scheck_cmd = ["maude-hcs", "scheck", "--test=" + str(generated_test_path.resolve()), f"--query={str(Path.joinpath(smc_path, query).resolve())}", "--format", "json", "-j", "0", f"-d{str(delta)}"]
            result[query]['scheck cmd'] = ' '.join([x for x in scheck_cmd])
            print(f'{result[query]['scheck cmd']}')
            start = time.perf_counter()
            scheck_output = subprocess.run(scheck_cmd, capture_output=True, text=True, check=True)
            end = time.perf_counter()
            print(f"time: {end - start:.2f} seconds")
            new_result = json.loads(scheck_output.stdout)
            T = end - start
            
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
    for file in files[:1]:
        path = Path(os.path.join(use_case_path, file))
        print(f'Processing {path.resolve()}')
        result = smc(path, Path.joinpath(result_path, f'{path.stem}'), smc_path)
        result_file = result_path.joinpath(f'{path.stem}.json')
        print(f'Writing result to {str(result_file.resolve())}')
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)

         

if __name__ == "__main__":
    main()