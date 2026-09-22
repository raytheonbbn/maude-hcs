from maude_hcs.compare_dists import *

def main():
    args = sys.argv
    if len(args) != 4:
         print(f'Expecting two arguments (1) the path of the directory with SMC results files, and (2) path of directory with experimental results files, and (3) path to result dir')
         sys.exit(1)
    smc_results_path = TOPLEVELDIR.joinpath(sys.argv[1])
    exp_results_path = TOPLEVELDIR.joinpath(sys.argv[2])    
    results_path = TOPLEVELDIR.joinpath(sys.argv[3])
    print(results_path)
    if not os.path.exists(results_path):
        os.mkdir(results_path)
    print(f'Loading SMC results from {smc_results_path}')
    smc_files = sorted(list(filter(lambda x: x.endswith('json'), os.listdir(smc_results_path))))
    exp_files = sorted(list(filter(lambda x: x.endswith('json'), os.listdir(exp_results_path))))
    for file in smc_files:
        print("\n" + "="*80 + "\n")
        path = Path(os.path.join(smc_results_path, file))
        name = path.stem
        exp_file = [f for f in exp_files if name in f]
        assert len(exp_file) == 1, f'expenting to find a matching experiment file with name {name}'
        exp_path = Path(os.path.join(exp_results_path, exp_file[0]))
        print(f'Processing {name} at smc path {path.resolve()} and exp path {exp_path.resolve()}')
        # get the mean and std from smc path
        with open(path, 'r') as f:
            data = json.load(f)
        latency_mean = float(data['latency.quatex']['smc']['queries'][0]['mean'])
        latency_std = float(data['latency.quatex']['smc']['queries'][0]['std'])
        latency_nsims = int(data['latency.quatex']['smc']['nsims'])
        print(f'Theoretical (SMC) stats: mean={latency_mean}, std={latency_std}, nsims={latency_nsims}')
        # get the samples fr
        latency_samples = []
        with open(exp_path, 'r') as f:
            data = json.load(f)
        ns = len(data[exp_path.stem])
        for i in range(ns):
            if str(i) in data[exp_path.stem]:
                if data[exp_path.stem][str(i)]["checksum_validation"]:
                    latency_samples.append(float(data[exp_path.stem][str(i)]['latency']))
        print(f'Experimental samples nsamples={len(latency_samples)}')
        print(latency_samples)
        print('\n')        
        # comparing two normal distributions: one is based on samples, the other is theoretical (mean, variance)
        figpath = Path(os.path.join(results_path, exp_path.stem))
        means_different, std_different = compare_experimental_to_smc(latency_samples, (latency_mean, latency_std), title=exp_path.stem, verbose=True, plot=True, results_dir=figpath)
        print(f'Means different?={means_different}, Std different?={std_different}')


if __name__ == '__main__':
    main()
    exit(0)
    # # Set the seed for reproducibility.
    # np.random.seed(42)

    # --- Generate Sample Data ---
    # Set the seed for reproducibility of the random samples.
    # np.random.seed(42)

    # ==============
    # CASE 1: comparing two normal distributions based on two sets of samples
    # ==============
    # # Scenario 1: Two samples from nearly identical distributions.
    # print("--- SCENARIO 1: Comparing two similar distributions ---")
    # sample_a1 = np.random.normal(loc=100, scale=15, size=500)
    # sample_a2 = np.random.normal(loc=102, scale=14, size=500)
    # compare_normal_distributions(sample_a1, sample_a2)
    # print("\n" + "="*50 + "\n")

    # # Scenario 2: Two samples from clearly different distributions.
    # print("--- SCENARIO 2: Comparing two different distributions ---")
    # sample_b1 = np.random.normal(loc=85, scale=10, size=500)
    # sample_b2 = np.random.normal(loc=115, scale=20, size=500)
    # compare_normal_distributions(sample_b1, sample_b2)



    # ==============
    # CASE 2: comparing two normal distributions: one is based on samples, the other is theoretical (mean, variance)
    # ==============
    # # --- Scenario 1: Sample is drawn from a distribution very similar to the theoretical one ---
    # print("--- SCENARIO 1: Comparing samples to a similar theoretical distribution ---")    
    # # TODO replace this with experimental samples (testing for now)
    # sample1 = np.random.normal(loc=90.5, scale=15.5, size=500)
    # # Define the theoretical distribution it should be similar to
    # theoretical1 = (90, 15) # (mean, std_dev)
    # means_different, std_different = compare_experimental_to_smc(sample1, theoretical1)
    # assert not means_different and not std_different, 'expecting same dist'
    # print("\n" + "="*80 + "\n")

    # # --- Scenario 2: Sample is drawn from a distribution clearly different from the theoretical one ---
    # print("--- SCENARIO 2: Comparing a sample to a different theoretical distribution ---")
    # # Generate a sample with a different mean and standard deviation
    # sample2 = np.random.normal(loc=110, scale=25, size=500)
    # means_different, std_different = compare_experimental_to_smc(sample2, theoretical1)
    # assert means_different and std_different, 'expecting different dist'


    # ==============
    # CASE 3: comparing two theoretical distributions each with (mean, variance); this is mostly visual
    # ==============
    # Define the parameters for two normal distributions
    # Format: (mean, standard_deviation)
    dist1_params = (100, 15, 'T&E')
    dist2_params = (115, 20, 'Maude-HCS SMC')

    print(f"Comparing Distribution 1 (μ={dist1_params[0]}, σ={dist1_params[1]}) with Distribution 2 (μ={dist2_params[0]}, σ={dist2_params[1]})")
    print("="*80)
    compare_theoretical_distributions(dist1_params, dist2_params)

    print("\n\n--- Comparing two identical distributions ---")
    dist3_params = (90, 10, 'T&E')
    dist4_params = (90, 10, 'Maude-HCS SMC')
    print(f"Comparing Distribution 3 (μ={dist3_params[0]}, σ={dist3_params[1]}) with Distribution 4 (μ={dist4_params[0]}, σ={dist4_params[1]})")
    print("="*80)
    compare_theoretical_distributions(dist3_params, dist4_params)
