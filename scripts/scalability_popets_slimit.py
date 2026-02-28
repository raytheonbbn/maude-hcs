import json
from pathlib import Path
import subprocess
import time
import itertools
from datetime import datetime
import sys
import os
import matplotlib.pyplot as plt
import shutil

TOPLEVELDIR = Path(os.path.dirname(__file__))

output_dir = "./results_popets_v2_slimit400/"

label_map = {
  3: "3 consecutive alarms",
  4: "4 consecutive alarms",
  5: "5 consecutive alarms"
}

#run_scenario= { 1,4,7,10 } 
run_scenario= { 7 } 

all = {
    "label": "all",
    "k": [1.2,1.4,1.6,1.8,2.0],
    "n": [3,4,5]
}

ma1_baseline = {
    "label": "ma1_baseline",
    "k": [1.2,1.4,1.6,1.8,2.0],
    "n": [3,4,5]
}

cli_wait = {
    "label": "cli_wait",
    "cli_wait_time": [2.0, 4.0, 8.0, 16.0, 32.0]
}

def smc(param_space, scenario_path, scenario_id, smc_path:Path, tgenonly=False, scheckonly=False):
    config_path = scenario_path + "/cp2_scenario_" + str(scenario_id) + "-hcsconfig.json" 
    with open(config_path, "r") as f:
        config = json.load(f)
    links = config.get("topology", {}).get("links", [])

    experiment = param_space.pop("label")
    if tgenonly:
        result_path = output_dir + "/cp2_scenario_" + str(scenario_id) + "_" + experiment + "_tgenonly.json" 
    else:
        result_path = output_dir + "/cp2_scenario_" + str(scenario_id) + "_" + experiment + ".json" 
    print(result_path)
    if not os.path.exists(result_path) or os.stat(result_path).st_size == 0:
        with open(result_path, "w") as f:
            json.dump({}, f)
        print("create experiments ", result_path)

    with open(result_path, "r") as f:
        result = json.load(f)

    keys = list(param_space.keys())
    vals = list(param_space.values())
    pairs = list(itertools.product(*vals))

    for p in pairs:
        params = dict(zip(keys, p))
        params_path = "_".join(f"{k}-{str(v)}" for k, v in params.items())
        result[params_path] = {}
        modified_config_path = output_dir + "cp2_scenario_" + str(scenario_id) + "-hcsconfig-" + params_path + ".json"
        generated_test_path = "cp2_scenario_" + str(scenario_id) + "-hcsconfig-" + params_path 
        for k, v in params.items():
            if k == "k":
                config["adversary"]["router_post_nat"]["scripts"][1]["params"]["k"] = v 
                result[params_path]["k"] = v 
            elif k == "n":   
                config["adversary"]["router_post_nat"]["scripts"][1]["params"]["n"] = v 
                result[params_path]["n"] = v 
            elif k == "cli_wait_time":
                result[params_path]["cli_wait_time"] = v

        with open(modified_config_path, "w") as f:
            json.dump(config, f, indent=2)
    
        print(generated_test_path)         

        if tgenonly:
            tgenonly_fn = scenario_path + "/" + generated_test_path + "_tgenonly.maude"
            subprocess.run(["cp", scenario_path + "/" + generated_test_path + ".maude", tgenonly_fn])
            subprocess.run(["sed", "-i", "/--- applications/,/--- WMonitor/ s/^/--- /", tgenonly_fn], check=True) 
            subprocess.run([ "sed", "-i", r"s/slimit[[:space:]]*=[[:space:]]*[0-9]*\.0/slimit = 400.0/", tgenonly_fn ], check=True)
        else:
            if not scheckonly:
                subprocess.run(["maude-hcs", "generate", "--run-args-file=" + modified_config_path, "--model=prob", "--filename=" + generated_test_path], stdout=subprocess.DEVNULL)

        if scheckonly:
            quatex_fn = str(smc_path) + "/cp2_eval_cp2_scenario_" + str(scenario_id) + ".quatex"
        else:
            quatex_fn = str(smc_path) + "/cp2_eval_" + generated_test_path + ".quatex"
        start = time.perf_counter()
        if tgenonly:
            scheck_cmd = ["maude-hcs", "scheck", "--test=" + scenario_path + "/" + generated_test_path + "_tgenonly.maude", "--query=" + quatex_fn, "--format", "json", "-j", "0", "--nsims", "300-300", "--dump", output_dir + "/cp2_scenario_" + str(scenario_id) + "_" + experiment + generated_test_path + "_tgenonly.dat"]
        else:
            subprocess.run([ "sed", "-i", r"s/slimit[[:space:]]*=[[:space:]]*[0-9]*\.0/slimit = 400.0/", scenario_path + "/" + generated_test_path + ".maude" ], check=True)
            scheck_cmd = ["maude-hcs", "scheck", "--test=" + scenario_path + "/" + generated_test_path + ".maude", "--query=" + quatex_fn, "--format", "json", "-j", "0", "--nsims", "300-300", "--dump", output_dir + "/cp2_scenario_" + str(scenario_id) + "_" + experiment + generated_test_path + ".dat"]
        print(' '.join([x for x in scheck_cmd]))
        scheck_output = subprocess.run(scheck_cmd, capture_output=True, text=True, check=True)
        end = time.perf_counter()
        #print(scheck_output.stdout)
        print(f"time: {end - start:.2f} seconds")
        new_result = json.loads(scheck_output.stdout)
        result[params_path]["scheck"] = new_result
        result[params_path]["time"] = end - start
        now = datetime.now()
        result[params_path]["now"] = now.isoformat() 
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)

        param_space["label"] = experiment 

def plot_three(param_space, xlabel, ylabel, key, vals, title, png_fn, scenario_id, tgenonly=False):
    metric_1 = []
    metric_2 = []
    metric_3 = []
    line_series_1 = []
    line_series_2 = []
    line_series_3 = []

    param_label = param_space.pop("label") 
    if tgenonly:
        result_path = output_dir + "/cp2_scenario_" + str(scenario_id) + "_" + param_label + "_tgenonly.json" 
    else:
        result_path = output_dir + "/cp2_scenario_" + str(scenario_id) + "_" + param_label + ".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        if ylabel == "Prob of Detection":
            query = v["scheck"]["queries"][7]
            if v[key] == vals[0]:
                metric_1.append(query["nsims"] / (query["discarded"] + query["nsims"]))
                line_series_1.append(v["k"])
            elif v[key] == vals[1]:
                metric_2.append(query["nsims"] / (query["discarded"] + query["nsims"]))
                line_series_2.append(v["k"])
            elif v[key] == vals[2]:
                metric_3.append(query["nsims"] / (query["discarded"] + query["nsims"]))
                line_series_3.append(v["k"])
            continue	
        if ylabel == "ExfilData":
            query0 = v["scheck"]["queries"][0]
            query1 = v["scheck"]["queries"][1]
            if v[key] == vals[0]:
                metric_1.append(query1["mean"] * query0["mean"])
                line_series_1.append(v["k"])
            elif v[key] == vals[1]:
                metric_2.append(query1["mean"] * query0["mean"])
                line_series_2.append(v["k"])
            elif v[key] == vals[2]:
                metric_3.append(query1["mean"] * query0["mean"])
                line_series_3.append(v["k"])
            continue
        elif ylabel == "Operating Duration (Seconds)":
            query = v["scheck"]["queries"][7]
        elif ylabel == "Num of Exfil Files":
            query = v["scheck"]["queries"][4]
        elif ylabel == "Latency":
            query = v["scheck"]["queries"][0] 
        elif ylabel == "Goodput":
            query = v["scheck"]["queries"][1] 
        if v[key] == vals[0]:
            metric_1.append(query["mean"])
            line_series_1.append(v["k"])
        elif v[key] == vals[1]:
            metric_2.append(query["mean"])
            line_series_2.append(v["k"])
        elif v[key] == vals[2]:
            metric_3.append(query["mean"])
            line_series_3.append(v["k"])

    #print(line_series_1)
    #print(line_series_2)
    #print(line_series_3)
    #print(metric_1)
    #print(metric_2)
    #print(metric_3)
    plt.figure(figsize=(7.5,4.5))
    plt.plot(line_series_1, metric_1, marker='o', linestyle='--', label=f"{label_map[3]}")
    plt.plot(line_series_2, metric_2, marker='o', linestyle='--', label=f"{label_map[4]}")
    plt.plot(line_series_3, metric_3, marker='o', linestyle='--', label=f"{label_map[5]}")
    plt.title(title)
    plt.xlabel(xlabel) 
    plt.ylabel(ylabel) 
    plt.legend()

    png_path = output_dir + "/" + png_fn 
    plt.savefig(png_path)
    print("saved to", png_path)
    plt.close()

    param_space["label"] = param_label 

def plot_cli_wait(param_space, xlabel, ylabel, title, png_fn, scenario_id, tgenonly=False):
    metric_1 = []
    line_series_1 = []

    param_label = param_space.pop("label")
    if tgenonly:
        result_path = output_dir + "/cp2_scenario_" + str(scenario_id) + "_" + param_label + "_tgenonly.json"
    else:
        result_path = output_dir + "/cp2_scenario_" + str(scenario_id) + "_" + param_label + ".json"
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        print (k)
        if ylabel == "ExfilData":
            query0 = v["scheck"]["queries"][0]
            query1 = v["scheck"]["queries"][1]
            metric_1.append(query1["mean"] * query0["mean"])
            line_series_1.append(v["cli_wait_time"])
            continue
        elif ylabel == "Latency":
            query = v["scheck"]["queries"][0]
        elif ylabel == "Goodput":
            query = v["scheck"]["queries"][1]
        elif ylabel == "Exfil_C2":
            query = v["scheck"]["queries"][2]
        elif ylabel == "Exfil_C8":
            query = v["scheck"]["queries"][3]
        elif ylabel == "Exfil_MA1":
            query = v["scheck"]["queries"][4]
        elif ylabel == "OpDur_C2":
            query = v["scheck"]["queries"][5]
        elif ylabel == "OpDur_C8":
            query = v["scheck"]["queries"][6]
        elif ylabel == "OpDur_MA1":
            query = v["scheck"]["queries"][7]
        elif ylabel == "PoD_C2":
            query = v["scheck"]["queries"][8]
        elif ylabel == "PoD_C8":
            query = v["scheck"]["queries"][9]
        elif ylabel == "PoD_MA1":
            query = v["scheck"]["queries"][10]
        metric_1.append(query["mean"])
        line_series_1.append(v["cli_wait_time"])

    #print(line_series_1)
    #print(metric_1)
    plt.figure(figsize=(7.5,4.5))
    plt.plot(line_series_1, metric_1, marker='o', linestyle='--', label="_no")
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    #plt.legend()

    png_path = output_dir + "/" + png_fn
    plt.savefig(png_path)
    print("saved to", png_path)
    plt.close()

    param_space["label"] = param_label

def main():
    os.makedirs(output_dir, exist_ok=True)

    args = sys.argv
    if len(args) != 2:
        print(f'Expecting one argument: path of the directory with maude scenario files')
        sys.exit(1)

    use_case_path = TOPLEVELDIR.joinpath(sys.argv[1])
    smc_path = TOPLEVELDIR.parent.joinpath('smc')

    # ma1 k,n params 
    for scenario_id in run_scenario:
        smc(ma1_baseline, str(use_case_path) + "/cp2_scenarios", scenario_id, smc_path)
        plot_three(ma1_baseline, "Detection Threshold", "Operating Duration (Seconds)", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " Operation Duration (MA.1)", "cp2_scenario_" + str(scenario_id) + "_op_ma1", scenario_id)
        plot_three(ma1_baseline, "Detection Threshold", "Num of Exfil Files", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " Number of ExfilFiles (MA.1)", "cp2_scenario_" + str(scenario_id) + "_exfil_ma1", scenario_id)
        plot_three(ma1_baseline, "Detection Threshold", "Prob of Detection", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " Prob of Detection (MA.1)", "cp2_scenario_" + str(scenario_id) + "_pod_ma1", scenario_id)
        plot_three(ma1_baseline, "Detection Threshold", "Latency", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " Latency (MA.1)", "cp2_scenario_" + str(scenario_id) + "_latency_ma1", scenario_id)
        plot_three(ma1_baseline, "Detection Threshold", "Goodput", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " Goodput (MA.1)", "cp2_scenario_" + str(scenario_id) + "_goodput_ma1", scenario_id)
        plot_three(ma1_baseline, "Detection Threshold", "ExfilData", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " ExfilData (MA.1)", "cp2_scenario_" + str(scenario_id) + "_exfildata_ma1", scenario_id)

    # ma1 k,n params tgenonly case
    for scenario_id in run_scenario:
        smc(ma1_baseline, str(use_case_path) + "/cp2_scenarios", scenario_id, smc_path, True)
        plot_three(ma1_baseline, "Detection Threshold", "Operating Duration (Seconds)", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " TGen Operation Duration (MA.1)", "cp2_scenario_" + str(scenario_id) + "_op_ma1_tgenonly", scenario_id, True)
        plot_three(ma1_baseline, "Detection Threshold", "Num of Exfil Files", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " TGen Number of ExfilFiles (MA.1)", "cp2_scenario_" + str(scenario_id) + "_exfil_ma1_tgenonly", scenario_id, True)
        plot_three(ma1_baseline, "Detection Threshold", "Prob of Detection", "n", [3,4,5], "CP2 Scenario " + str(scenario_id) + " TGen Prob of Detection (MA.1)", "cp2_scenario_" + str(scenario_id) + "_pod_ma1_tgenonly", scenario_id, True)

    # cli wait time
    for scenario_id in run_scenario:
        smc(cli_wait, str(use_case_path) + "/cp2_scenarios", scenario_id, smc_path, False, True)
        plot_cli_wait(cli_wait, "Client Wait Time", "Latency", "CP2 Scenario " + str(scenario_id) + " Latency", "cp2_scenario_" + str(scenario_id) + "_cli_wait_latency", scenario_id, False)
        plot_cli_wait(cli_wait, "Client Wait Time", "Goodput", "CP2 Scenario " + str(scenario_id) + " Goodput", "cp2_scenario_" + str(scenario_id) + "_cli_wait_goodput", scenario_id, False)
        plot_cli_wait(cli_wait, "Client Wait Time", "OpDur_C2", "CP2 Scenario " + str(scenario_id) + " OpDur C2", "cp2_scenario_" + str(scenario_id) + "_cli_wait_opdur_c2", scenario_id, False)
        plot_cli_wait(cli_wait, "Client Wait Time", "PoD_C2", "CP2 Scenario " + str(scenario_id) + " PoD C2", "cp2_scenario_" + str(scenario_id) + "_cli_wait_pod_c2", scenario_id, False)
        plot_cli_wait(cli_wait, "Client Wait Time", "OpDur_C8", "CP2 Scenario " + str(scenario_id) + " OpDur C8", "cp2_scenario_" + str(scenario_id) + "_cli_wait_opdur_c8", scenario_id, False)
        plot_cli_wait(cli_wait, "Client Wait Time", "PoD_C8", "CP2 Scenario " + str(scenario_id) + " PoD C8", "cp2_scenario_" + str(scenario_id) + "_cli_wait_pod_c8", scenario_id, False)
        plot_cli_wait(cli_wait, "Client Wait Time", "OpDur_MA1", "CP2 Scenario " + str(scenario_id) + " OpDur MA1", "cp2_scenario_" + str(scenario_id) + "_cli_wait_opdur_ma1", scenario_id, False)
        plot_cli_wait(cli_wait, "Client Wait Time", "PoD_MA1", "CP2 Scenario " + str(scenario_id) + " PoD MA1", "cp2_scenario_" + str(scenario_id) + "_cli_wait_pod_ma1", scenario_id, False)

    # cli wait time tgenonly case 
    for scenario_id in run_scenario:
        smc(cli_wait, str(use_case_path) + "/cp2_scenarios", scenario_id, smc_path, True, True)
        plot_cli_wait(cli_wait, "Client Wait Time", "OpDur_C2", "CP2 Scenario " + str(scenario_id) + " TGen OpDur C2", "cp2_scenario_" + str(scenario_id) + "_cli_wait_opdur_c2_tgenonly", scenario_id, True)
        plot_cli_wait(cli_wait, "Client Wait Time", "PoD_C2", "CP2 Scenario " + str(scenario_id) + " TGen PoD C2", "cp2_scenario_" + str(scenario_id) + "_cli_wait_pod_c2_tgenonly", scenario_id, True)
        plot_cli_wait(cli_wait, "Client Wait Time", "OpDur_C8", "CP2 Scenario " + str(scenario_id) + " TGen OpDur C8", "cp2_scenario_" + str(scenario_id) + "_cli_wait_opdur_c8_tgenonly", scenario_id, True)
        plot_cli_wait(cli_wait, "Client Wait Time", "PoD_C8", "CP2 Scenario " + str(scenario_id) + " TGen PoD C8", "cp2_scenario_" + str(scenario_id) + "_cli_wait_pod_c8_tgenonly", scenario_id, True)
        plot_cli_wait(cli_wait, "Client Wait Time", "OpDur_MA1", "CP2 Scenario " + str(scenario_id) + " TGen OpDur MA1", "cp2_scenario_" + str(scenario_id) + "_cli_wait_opdur_ma1_tgenonly", scenario_id, True)
        plot_cli_wait(cli_wait, "Client Wait Time", "PoD_MA1", "CP2 Scenario " + str(scenario_id) + " TGen PoD MA1", "cp2_scenario_" + str(scenario_id) + "_cli_wait_pod_ma1_tgenonly", scenario_id, True)

if __name__ == "__main__":
    main()
