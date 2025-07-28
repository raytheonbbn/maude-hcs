import json
import subprocess
import time
import itertools
from datetime import datetime
import sys
import os
import matplotlib.pyplot as plt
import shutil

output_dir ="./results"

all = {
    "label": "all",
    "dnsperfNodes": [0,1],
    "dnsperfMaxQPS": [15,30,50],
    "dnsperfTlimit": [2],   # needs to be set to the max
    "app_pacing": [0.505,0.01],
    "pub_svr_drop": [0,10,20,30],
    "loc_pub_drop": [0,10,20,30],
    "cli_loc_drop": [0,10,20,30],
    "fragSize": [180,188],
    "chunkSize": [530,991],
    "fileSize": [1000,2000,4000,8000,16000]
}

baseline = {
    "label": "baseline",
    "dnsperfNodes": [0],
    "app_pacing": [0.01],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000,16000]
}

app_pacing = {
    "label": "app_pacing",
    "dnsperfNodes": [0],
    "app_pacing": [0.505,0.01],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000,16000]
}

pub_svr_drop = {
    "label": "pub_svr_drop",
    "dnsperfNodes": [0],
    "app_pacing": [0.01],
    "pub_svr_drop": [0,10,20,30],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000,16000]
}

loc_pub_drop = {
    "label": "loc_pub_drop",
    "dnsperfNodes": [0],
    "app_pacing": [0.01],
    "loc_pub_drop": [0,10,20,30],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000,16000]
}

cli_loc_drop = {
    "label": "cli_loc_drop",
    "dnsperfNodes": [0],
    "app_pacing": [0.01],
    "cli_loc_drop": [0,10,20,30],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000,16000]
}

cli_loc_pub_svr_drop = {
    "label": "cli_loc_pub_svr_drop",
    "dnsperfNodes": [0],
    "app_pacing": [0.01],
    "pub_svr_drop": [0,10],
    "loc_pub_drop": [0,10],
    "cli_loc_drop": [0,10],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000]
}

dnsperf = {
    "label": "dnsperf",
    "dnsperfNodes": [1],
    "dnsperfMaxQPS": [15,30,50],
    "dnsperfTlimit": [2],   # needs to be set to the max
    "app_pacing": [0.01],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000]
}

dnsperf_pub_svr_drop = {
    "label": "dnsperf_pub_svr_drop",
    "dnsperfNodes": [1],
    "dnsperfMaxQPS": [15,30,50],
    "dnsperfTlimit": [20],   # needs to be set to the max
    "app_pacing": [0.01],
    "pub_svr_drop": [10],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000]
}

dnsperf_loc_pub_drop = {
    "label": "dnsperf_loc_pub_drop",
    "dnsperfNodes": [1],
    "dnsperfMaxQPS": [15,30,50],
    "dnsperfTlimit": [20],   # needs to be set to the max
    "app_pacing": [0.01],
    "loc_pub_drop": [10],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000]
}

dnsperf_cli_loc_drop = {
    "label": "dnsperf_cli_loc_drop",
    "dnsperfNodes": [1],
    "dnsperfMaxQPS": [15,30,50],
    "dnsperfTlimit": [20],   # needs to be set to the max
    "app_pacing": [0.01],
    "cli_loc_drop": [10],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000]
}

dnsperf_cli_loc_pub_svr_drop = {
    "label": "dnsperf_cli_loc_pub_svr_drop",
    "dnsperfNodes": [1],
    "dnsperfMaxQPS": [15],
    "dnsperfTlimit": [60],   # needs to be set to the max
    "app_pacing": [0.01],
    "pub_svr_drop": [0,10],
    "loc_pub_drop": [0,10],
    "cli_loc_drop": [0,10],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1000,2000,4000,8000]
}

dnsperf_query = {
    "label": "dnsperf_query",
    "dnsperfNodes": [1],
    "dnsperfMaxQPS": [15,30,50,75,100],
    "dnsperfTlimit": [20],   # needs to be set to the max
    "app_pacing": [0.01],
    "pub_svr_drop": [0,10],
    "fragSize": [180],
    "chunkSize": [530],
    "fileSize": [1,8000]
}

def smc(param_space, delta=0.5, alpha=0.05, fixed=True, hybrid=False, seq=False):
    config_path = "../use-cases/corporate-iodine-conf.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    links = config.get("topology", {}).get("links", [])

    experiment = param_space.pop("label")
    result_path = output_dir + "/" + experiment + "-delta-" + str(delta) + "-alpha-" + str(alpha) +".json" 
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
        modified_config_path = output_dir + "/corporate-iodine-conf-" + params_path + ".json"
        generated_test_path = "corporate-iodine-conf-" + params_path 
        for k, v in params.items():
            if k == "fileSize":
                config["nondeterministic_parameters"]["fileSize"] = v 
                result[params_path]["fileSize"] = v 
            elif k == "dnsperfMaxQPS":   
                config["background_traffic"]["paced_client_MaxQPS"] = v 
                result[params_path]["paced_client_MaxQPS"] = v 
            elif k == "dnsperfNodes":
                config["background_traffic"]["num_paced_clients"] = v
                result[params_path]["num_paced_clients"] = v 
            elif k == "dnsperfTlimit":
                config["background_traffic"]["paced_client_Tlimit"] = v
                result[params_path]["paced_client_Tlimit"] = v 
            elif k == "pub_svr_drop":
                for l in links:
                    if l.get("label") == "public_dns to application_server":
                        l["loss"] = v
                result[params_path]["pub_svr_drop"] = v 
            elif k == "loc_pub_drop":
                for l in links:
                    if l.get("label") == "public_dns to local_dns": 
                        l["loss"] = v
                result[params_path]["loc_pub_drop"] = v 
            elif k == "cli_loc_drop":
                for l in links:
                    if l.get("label") == "local_dns to application_client":
                        l["loss"] = v
                result[params_path]["cli_loc_drop"] = v 
            elif k == "app_pacing":
                config["probabilistic_parameters"]["pacingTimeoutDelay"] = v
                config["probabilistic_parameters"]["pacingTimeoutDelayMax"] = v
                result[params_path]["pacingTimeoutDelay"] = v
                result[params_path]["pacingTimeoutDelayMax"] = v
            elif k == "chunkSize":
                config["nondeterministic_parameters"]["packetSize"] = v
                config["nondeterministic_parameters"]["maxPacketSize"] = v
                result[params_path]["packetSize"] = v
                result[params_path]["maxPacketSize"] = v
            elif k == "fragSize":
                config["nondeterministic_parameters"]["maxFragmentLen"] = v
                result[params_path]["maxFragmentLen"] = v

        with open(modified_config_path, "w") as f:
            json.dump(config, f, indent=2)
    
        print(generated_test_path)         
        subprocess.run(["maude-hcs", "--run-args=" + modified_config_path, "--model=prob", "--filename=" + generated_test_path, "generate"], stdout=subprocess.DEVNULL)

        if hybrid == True: 
            scheck_output = subprocess.run(["maude-hcs", "scheck", "--test=./results/" + generated_test_path + ".maude", "--format", "json", "-j", "0", "-d" + str(delta), "-a" + str(alpha), "--seed", "0", "--nsims" ,"30-30"], capture_output=True, text=True, check=True)
            tmp_result = json.loads(scheck_output.stdout)
            query = tmp_result["queries"][0]
            delta_estimate = 0.05 * query["mean"]
            delta = delta_estimate

        if fixed == True or hybrid == True:
            nsim_range = str("30-100")
        else: 
            nsim_range = str("30-")
        start = time.perf_counter()

        scheck_output = subprocess.run(["maude-hcs", "scheck", "--test=./results/" + generated_test_path + ".maude", "--format", "json", "-j", "0", "-d" + str(delta), "-a" + str(alpha), "--seed", "0", "--nsims", nsim_range], capture_output=True, text=True, check=True)
        end = time.perf_counter()
        print(f"time: {end - start:.2f} seconds")
        new_result = json.loads(scheck_output.stdout)
        result[params_path]["scheck"] = new_result
        result[params_path]["time"] = end - start
        now = datetime.now()
        result[params_path]["now"] = now.isoformat() 
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)

        param_space["label"] = experiment 

def plot_baseline(param_space, delta=0.5, alpha=0.05):
    latencys = []
    filesizes = []

    param_label = param_space.pop("label") 
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        query = v["scheck"]["queries"][0]
        latencys.append(query["mean"])
        filesizes.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    #plt.scatter(filesizes, latencys, c='blue')
    plt.plot(filesizes, latencys, marker='o', linestyle='--')
    plt.title("Baseline Performance (AppPacing 0.01 Seconds, FragSize 180 Bytes, ChunkSize 530 Bytes)")
    plt.xlabel("FileSize (Bytes)") 
    plt.ylabel("Latency (Seconds)") 

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".png"
    plt.savefig(png_path)
    print("saved to", png_path)
    
    param_space["label"] = param_label 

def plot_two(param_space, key, vals, title, delta=0.5, alpha=0.05):
    latencys_1 = []
    latencys_2 = []
    filesize_1 = []
    filesize_2 = []

    param_label = param_space.pop("label") 
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        query = v["scheck"]["queries"][0]
        if v[key] == vals[0]:
            latencys_1.append(query["mean"])
            filesize_1.append(v["fileSize"])
        elif v[key] == vals[1]:
            latencys_2.append(query["mean"])
            filesize_2.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(filesize_1, latencys_1, marker='o', linestyle='--', label=str(vals[0]))
    plt.plot(filesize_2, latencys_2, marker='o', linestyle='--', label=str(vals[1]))
    plt.title(title)
    plt.xlabel("FileSize (Bytes)") 
    plt.ylabel("Latency (Seconds)") 
    plt.legend()

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".png"
    plt.savefig(png_path)
    print("saved to", png_path)
    
    param_space["label"] = param_label 

def plot_four(param_space, key, vals, title, delta=0.5, alpha=0.05):
    latencys_1 = []
    latencys_2 = []
    latencys_3 = []
    latencys_4 = []
    filesize_1 = []
    filesize_2 = []
    filesize_3 = []
    filesize_4 = []

    param_label = param_space.pop("label") 
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        query = v["scheck"]["queries"][0]
        if v[key] == vals[0]:
            latencys_1.append(query["mean"])
            filesize_1.append(v["fileSize"])
        elif v[key] == vals[1]:
            latencys_2.append(query["mean"])
            filesize_2.append(v["fileSize"])
        elif v[key] == vals[2]:
            latencys_3.append(query["mean"])
            filesize_3.append(v["fileSize"])
        elif v[key] == vals[3]:
            latencys_4.append(query["mean"])
            filesize_4.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(filesize_1, latencys_1, marker='o', linestyle='--', label=str(vals[0]))
    plt.plot(filesize_2, latencys_2, marker='o', linestyle='--', label=str(vals[1]))
    plt.plot(filesize_3, latencys_3, marker='o', linestyle='--', label=str(vals[2]))
    plt.plot(filesize_4, latencys_4, marker='o', linestyle='--', label=str(vals[3]))
    plt.title(title)
    plt.xlabel("FileSize (Bytes)") 
    plt.ylabel("Latency (Seconds)") 
    plt.legend()

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".png"
    plt.savefig(png_path)
    print("saved to", png_path)

    param_space["label"] = param_label 

def plot_link_drop(param_space, title, delta=0.5, alpha=0.05):
    latencys_1 = []
    latencys_2 = []
    latencys_3 = []
    latencys_4 = []
    latencys_5 = []
    latencys_6 = []
    latencys_7 = []
    latencys_8 = []
    filesize_1 = []
    filesize_2 = []
    filesize_3 = []
    filesize_4 = []
    filesize_5 = []
    filesize_6 = []
    filesize_7 = []
    filesize_8 = []

    param_label = param_space.pop("label")
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json"
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        query = v["scheck"]["queries"][0]
        if v["pub_svr_drop"] == 0 and v["loc_pub_drop"] == 0 and v["cli_loc_drop"] == 0:
            latencys_1.append(query["mean"])
            filesize_1.append(v["fileSize"])
        elif v["pub_svr_drop"] == 0 and v["loc_pub_drop"] == 0 and v["cli_loc_drop"] == 10:
            latencys_2.append(query["mean"])
            filesize_2.append(v["fileSize"])
        elif v["pub_svr_drop"] == 0 and v["loc_pub_drop"] == 10 and v["cli_loc_drop"] == 0:
            latencys_3.append(query["mean"])
            filesize_3.append(v["fileSize"])
        elif v["pub_svr_drop"] == 0 and v["loc_pub_drop"] == 10 and v["cli_loc_drop"] == 10:
            latencys_4.append(query["mean"])
            filesize_4.append(v["fileSize"])
        elif v["pub_svr_drop"] == 10 and v["loc_pub_drop"] == 0 and v["cli_loc_drop"] == 0:
            latencys_5.append(query["mean"])
            filesize_5.append(v["fileSize"])
        elif v["pub_svr_drop"] == 10 and v["loc_pub_drop"] == 0 and v["cli_loc_drop"] == 10:
            latencys_6.append(query["mean"])
            filesize_6.append(v["fileSize"])
        elif v["pub_svr_drop"] == 10 and v["loc_pub_drop"] == 10 and v["cli_loc_drop"] == 0:
            latencys_7.append(query["mean"])
            filesize_7.append(v["fileSize"])
        elif v["pub_svr_drop"] == 10 and v["loc_pub_drop"] == 10 and v["cli_loc_drop"] == 10:
            latencys_8.append(query["mean"])
            filesize_8.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(filesize_1, latencys_1, marker='o', linestyle='--', label=" 0,  0,  0")
    plt.plot(filesize_2, latencys_2, marker='x', linestyle='--', label=" 0,  0, 10")
    plt.plot(filesize_3, latencys_3, marker='x', linestyle='--', label=" 0, 10,  0")
    plt.plot(filesize_5, latencys_5, marker='x', linestyle='--', label="10,  0,  0")
    plt.plot(filesize_4, latencys_4, marker='^', linestyle='--', label=" 0, 10, 10")
    plt.plot(filesize_6, latencys_6, marker='^', linestyle='--', label="10,  0, 10")
    plt.plot(filesize_7, latencys_7, marker='^', linestyle='--', label="10, 10,  0")
    plt.plot(filesize_8, latencys_8, marker='o', linestyle='--', label="10, 10, 10")
    plt.title(title)
    plt.xlabel("FileSize (Bytes)")
    plt.ylabel("Latency (Seconds)")
    legend = plt.legend()

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".png"
    plt.savefig(png_path)
    print("saved to", png_path)

    param_space["label"] = param_label

def plot_three(param_space, key, vals, title, delta=0.5, alpha=0.05):
    latencys_1 = []
    latencys_2 = []
    latencys_3 = []
    filesize_1 = []
    filesize_2 = []
    filesize_3 = []

    param_label = param_space.pop("label") 
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        query = v["scheck"]["queries"][0]
        if v[key] == vals[0]:
            latencys_1.append(query["mean"])
            filesize_1.append(v["fileSize"])
        elif v[key] == vals[1]:
            latencys_2.append(query["mean"])
            filesize_2.append(v["fileSize"])
        elif v[key] == vals[2]:
            latencys_3.append(query["mean"])
            filesize_3.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(filesize_1, latencys_1, marker='o', linestyle='--', label=str(vals[0]))
    plt.plot(filesize_2, latencys_2, marker='o', linestyle='--', label=str(vals[1]))
    plt.plot(filesize_3, latencys_3, marker='o', linestyle='--', label=str(vals[2]))
    plt.title(title)
    plt.xlabel("FileSize (Bytes)") 
    plt.ylabel("Latency (Seconds)") 
    plt.legend()

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".png"
    plt.savefig(png_path)
    print("saved to", png_path)

    param_space["label"] = param_label 

def plot_loss_latency(param_space, key, vals, output_fn, title, delta=0.5, alpha=0.05):
    latencys_1 = []
    latencys_2 = []
    latencys_3 = []
    latencys_4 = []
    latencys_5 = []
    loss_1 = []
    loss_2 = []
    loss_3 = []
    loss_4 = []
    loss_5 = []

    param_label = param_space.pop("label")
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json"
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        query = v["scheck"]["queries"][0]
        if v[key] == vals[0]:
            latencys_1.append(query["mean"])
            loss_1.append(v["pub_svr_drop"])
        if v[key] == vals[1]:
            latencys_2.append(query["mean"])
            loss_2.append(v["pub_svr_drop"])
        if v[key] == vals[2]:
            latencys_3.append(query["mean"])
            loss_3.append(v["pub_svr_drop"])
        if v[key] == vals[3]:
            latencys_4.append(query["mean"])
            loss_4.append(v["pub_svr_drop"])
        if v[key] == vals[4]:
            latencys_5.append(query["mean"])
            loss_5.append(v["pub_svr_drop"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(loss_1, latencys_1, marker='o', linestyle='--', label=str(vals[0]))
    plt.plot(loss_2, latencys_2, marker='o', linestyle='--', label=str(vals[1]))
    plt.plot(loss_3, latencys_3, marker='o', linestyle='--', label=str(vals[2]))
    plt.plot(loss_4, latencys_4, marker='o', linestyle='--', label=str(vals[3]))
    plt.plot(loss_5, latencys_5, marker='o', linestyle='--', label=str(vals[4]))
    plt.title(title)
    plt.xlabel("Public <-> Server Link Loss (%)")
    plt.ylabel("Latency (Seconds)")
    plt.legend()

    png_path = output_dir + "/" + output_fn + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".png"
    plt.savefig(png_path)
    print("saved to", png_path)

    param_space["label"] = param_label 

def plot_smc_time(param_space, key, vals, title, delta=0.5, alpha=0.05):
    time_1 = []
    time_2 = []
    time_3 = []
    time_4 = []
    filesize_1 = []
    filesize_2 = []
    filesize_3 = []
    filesize_4 = []

    param_label = param_space.pop("label") 
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        if v[key] == vals[0]:
            time_1.append(v["time"])
            filesize_1.append(v["fileSize"])
        elif v[key] == vals[1]:
            time_2.append(v["time"])
            filesize_2.append(v["fileSize"])
        elif v[key] == vals[2]:
            time_3.append(v["time"])
            filesize_3.append(v["fileSize"])
        elif v[key] == vals[3]:
            time_4.append(v["time"])
            filesize_4.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(filesize_1, time_1, marker='o', linestyle='--', label=str(vals[0]))
    plt.plot(filesize_2, time_2, marker='o', linestyle='--', label=str(vals[1]))
    plt.plot(filesize_3, time_3, marker='o', linestyle='--', label=str(vals[2]))
    plt.plot(filesize_4, time_4, marker='o', linestyle='--', label=str(vals[3]))
    plt.title(title)
    plt.xlabel("FileSize (Bytes)") 
    plt.ylabel("SMC Runtime (Seconds)") 
    plt.legend()

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + "_smc_time.png"
    plt.savefig(png_path)
    print("saved to", png_path)

    param_space["label"] = param_label 

def plot_smc_nsim(param_space, key, vals, title, delta=0.5, alpha=0.05):
    time_1 = []
    time_2 = []
    time_3 = []
    time_4 = []
    filesize_1 = []
    filesize_2 = []
    filesize_3 = []
    filesize_4 = []

    param_label = param_space.pop("label") 
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        if v[key] == vals[0]:
            time_1.append(v["scheck"]["nsims"])
            filesize_1.append(v["fileSize"])
        elif v[key] == vals[1]:
            time_2.append(v["scheck"]["nsims"])
            filesize_2.append(v["fileSize"])
        elif v[key] == vals[2]:
            time_3.append(v["scheck"]["nsims"])
            filesize_3.append(v["fileSize"])
        elif v[key] == vals[3]:
            time_4.append(v["scheck"]["nsims"])
            filesize_4.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(filesize_1, time_1, marker='o', linestyle='--', label=str(vals[0]))
    plt.plot(filesize_2, time_2, marker='o', linestyle='--', label=str(vals[1]))
    plt.plot(filesize_3, time_3, marker='o', linestyle='--', label=str(vals[2]))
    plt.plot(filesize_4, time_4, marker='o', linestyle='--', label=str(vals[3]))
    plt.title(title)
    plt.xlabel("FileSize (Bytes)") 
    plt.ylabel("SMC Number of Samples") 
    plt.legend()

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + "_smc_nsim.png"
    plt.savefig(png_path)
    print("saved to", png_path)

    param_space["label"] = param_label 

def plot_smc_time_dnsperf(param_space, key, vals, title, delta=0.5, alpha=0.05):
    time_1 = []
    time_2 = []
    time_3 = []
    filesize_1 = []
    filesize_2 = []
    filesize_3 = []

    param_label = param_space.pop("label") 
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + ".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        if v[key] == vals[0]:
            time_1.append(v["time"])
            filesize_1.append(v["fileSize"])
        elif v[key] == vals[1]:
            time_2.append(v["time"])
            filesize_2.append(v["fileSize"])
        elif v[key] == vals[2]:
            time_3.append(v["time"])
            filesize_3.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(filesize_1, time_1, marker='o', linestyle='--', label=str(vals[0]))
    plt.plot(filesize_2, time_2, marker='o', linestyle='--', label=str(vals[1]))
    plt.plot(filesize_3, time_3, marker='o', linestyle='--', label=str(vals[2]))
    plt.title(title)
    plt.xlabel("FileSize (Bytes)") 
    plt.ylabel("SMC Runtime (Seconds)") 
    plt.legend()

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + "_smc_time.png"
    plt.savefig(png_path)
    print("saved to", png_path)

    param_space["label"] = param_label 

def plot_smc_nsim_dnsperf(param_space, key, vals, title, delta=0.5, alpha=0.05):
    time_1 = []
    time_2 = []
    time_3 = []
    filesize_1 = []
    filesize_2 = []
    filesize_3 = []

    param_label = param_space.pop("label") 
    result_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) +".json" 
    with open(result_path, "r") as f:
        result = json.load(f)
        print("loaded data from", result_path)

    for k, v in result.items():
        if v[key] == vals[0]:
            time_1.append(v["scheck"]["nsims"])
            filesize_1.append(v["fileSize"])
        elif v[key] == vals[1]:
            time_2.append(v["scheck"]["nsims"])
            filesize_2.append(v["fileSize"])
        elif v[key] == vals[2]:
            time_3.append(v["scheck"]["nsims"])
            filesize_3.append(v["fileSize"])

    plt.figure(figsize=(7.5,4.5))
    plt.plot(filesize_1, time_1, marker='o', linestyle='--', label=str(vals[0]))
    plt.plot(filesize_2, time_2, marker='o', linestyle='--', label=str(vals[1]))
    plt.plot(filesize_3, time_3, marker='o', linestyle='--', label=str(vals[2]))
    plt.title(title)
    plt.xlabel("FileSize (Bytes)") 
    plt.ylabel("SMC Number of Samples (Seconds)") 
    plt.legend()

    png_path = output_dir + "/" + param_label + "-delta-" + str(delta) + "-alpha-" + str(alpha) + "_smc_nsim.png"
    plt.savefig(png_path)
    print("saved to", png_path)

    param_space["label"] = param_label 

def main():
    os.makedirs(output_dir, exist_ok=True)
    if not os.path.isdir("./smc"):
        print("please create a symlink to smc directory, i.e., ln -s ../smc")
        sys.exit()

    smc(baseline)
    plot_baseline(baseline)

    smc(app_pacing)
    plot_two(app_pacing, "pacingTimeoutDelay", [0.01,0.505], "Performance with App Pacing (Seconds)")

    smc(pub_svr_drop)
    smc(loc_pub_drop)
    smc(cli_loc_drop)
    smc(cli_loc_pub_svr_drop)
    plot_four(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "Performance with Public <-> Server Link Loss (%)") 
    plot_four(loc_pub_drop, "loc_pub_drop", [0,10,20,30], "Performance with Local <-> Public Link Loss (%)") 
    plot_four(cli_loc_drop, "cli_loc_drop", [0,10,20,30], "Performance with Client <-> Local Link Loss (%)") 
    plot_link_drop(cli_loc_pub_svr_drop, "Performance with Combined Link Loss (%)\n Public <-> Server, Local <-> Public, Client <-> Local")

    smc(dnsperf)
    smc(dnsperf_pub_svr_drop)
    smc(dnsperf_loc_pub_drop)
    smc(dnsperf_cli_loc_drop)
    smc(dnsperf_cli_loc_pub_svr_drop)
    plot_three(dnsperf, "paced_client_MaxQPS", [15,30,50], "Performance with Background Traffic (QPS)")
    plot_three(dnsperf_pub_svr_drop, "paced_client_MaxQPS", [15,30,50], "Performance with Background Traffic (QPS) and Public <-> Server Link Loss (10 %)")
    plot_three(dnsperf_loc_pub_drop, "paced_client_MaxQPS", [15,30,50], "Performance with Background Traffic (QPS) and Local <-> Public Link Loss (10 %)")
    plot_three(dnsperf_cli_loc_drop, "paced_client_MaxQPS", [15,30,50], "Performance with Background Traffic (QPS) and Client <-> Local Link Loss (10 %)")
    plot_link_drop(dnsperf_cli_loc_pub_svr_drop, "Performance with Background Traffic and Combined Link Loss (%)\n Public <-> Server, Local <-> Public, Client <-> Local")

    plot_loss_latency(pub_svr_drop, "fileSize", [1000,2000,4000,8000,16000], "loss_latency", "Performance with Input File Size (Bytes)")

    plot_smc_time(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Runtime with Public <-> Server Link Loss (%)")
    plot_smc_nsim(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Number of Samples with Public <-> Server Link Loss (%)")
    plot_smc_time_dnsperf(dnsperf_pub_svr_drop, "paced_client_MaxQPS", [15,30,50], "SMC Runtime with Background Traffic (QPS) and Public <-> Server Link Loss (10 %)")
    plot_smc_nsim_dnsperf(dnsperf_pub_svr_drop, "paced_client_MaxQPS", [15,30,50], "SMC Number of Samples with Background Traffic (QPS) and Public <-> Server Link Loss (10 %)")

    smc(pub_svr_drop, delta=1)
    smc(pub_svr_drop, delta=5)
    plot_four(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "Performance (Delta=1) with Public <-> Server Link Loss (%)", 1) 
    plot_four(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "Performance (Delta=5) with Public <-> Server Link Loss (%)", 5) 
    plot_smc_time(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Runtime (Delta=1) with Public <-> Server Link Loss (%)", 1)
    plot_smc_time(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Runtime (Delta=5) with Public <-> Server Link Loss (%)", 5)
    plot_smc_nsim(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Number of Samples (Delta=1) with Public <-> Server Link Loss (%)", 1)
    plot_smc_nsim(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Number of Samples (Delta=5) with Public <-> Server Link Loss (%)", 5)

    plot_smc_time_dnsperf(dnsperf_pub_svr_drop, "paced_client_MaxQPS", [15,30,50], "SMC Runtime with Background Traffic (QPS) and Public <-> Server Link Loss (10 %)")
    plot_smc_nsim_dnsperf(dnsperf_pub_svr_drop, "paced_client_MaxQPS", [15,30,50], "SMC Number of Samples with Background Traffic (QPS) and Public <-> Server Link Loss (10 %)")

    smc(dnsperf_query)

    smc(pub_svr_drop, alpha=0.1)
    smc(pub_svr_drop, alpha=0.01)
    plot_four(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "Performance (Alpha=0.1) with Public <-> Server Link Loss (%)", alpha=0.1) 
    plot_four(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "Performance (Alpha=0.01) with Public <-> Server Link Loss (%)", alpha=0.01) 
    plot_smc_time(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Runtime (Alpha=0.1) with Public <-> Server Link Loss (%)", alpha=0.1)
    plot_smc_time(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Runtime (Alpha=0.01) with Public <-> Server Link Loss (%)", alpha=0.01)
    plot_smc_nsim(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Number of Samples (Alpha=0.1) with Public <-> Server Link Loss (%)", alpha=0.1)
    plot_smc_nsim(pub_svr_drop, "pub_svr_drop", [0,10,20,30], "SMC Number of Samples (Alpha=0.01) with Public <-> Server Link Loss (%)", alpha=0.01)

if __name__ == "__main__":
    main()
