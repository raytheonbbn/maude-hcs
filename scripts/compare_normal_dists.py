import json
import os
from pathlib import Path
import sys
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

TOPLEVELDIR = Path(os.path.dirname(__file__))

def kl_divergence_normal(params1, params2):
    """
    Calculates the Kullback-Leibler (KL) divergence between two normal distributions.
    KL(P || Q) where P is dist1 and Q is dist2.

    Args:
        params1 (tuple): (mean, std_dev) for the first distribution (P).
        params2 (tuple): (mean, std_dev) for the second distribution (Q).

    Returns:
        float: The KL divergence from P to Q.
    """
    mean1, std1, name1 = params1
    mean2, std2, name2 = params2

    # Ensure standard deviations are positive
    if std1 <= 0 or std2 <= 0:
        raise ValueError("Standard deviations must be positive.")

    var1 = std1**2
    var2 = std2**2

    # Formula for KL divergence between two normal distributions
    kl_div = np.log(std2 / std1) + (var1 + (mean1 - mean2)**2) / (2 * var2) - 0.5

    return kl_div

def compare_theoretical_distributions(params1, params2, title="Comparison of Two Theoretical Distributions"):
    """
    Visualizes and quantifies the difference between two theoretical normal distributions.

    Args:
        params1 (tuple): A tuple containing the (mean, std_dev, name) for the first distribution.
        params2 (tuple): A tuple containing the (mean, std_dev, name) for the second distribution.
        name above is the name of the distribution in the plot
    """
    mean1, std1, name1 = params1
    mean2, std2, name2 = params2

    # --- 1. Visualization ---
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))

    # Determine a good range for the x-axis to see both distributions
    x_min = min(mean1 - 4 * std1, mean2 - 4 * std2)
    x_max = max(mean1 + 4 * std1, mean2 + 4 * std2)
    x = np.linspace(x_min, x_max, 500)

    # Calculate the PDFs
    pdf1 = stats.norm.pdf(x, mean1, std1)
    pdf2 = stats.norm.pdf(x, mean2, std2)

    # Plot the PDFs
    ax.plot(x, pdf1, lw=2, label=f'{name1}: N(μ={mean1}, σ={std1})', color='skyblue')
    ax.fill_between(x, pdf1, alpha=0.2, color='skyblue')
    ax.plot(x, pdf2, lw=2, label=f'{name2}: N(μ={mean2}, σ={std2})', color='salmon')
    ax.fill_between(x, pdf2, alpha=0.2, color='salmon')

    ax.set_title(title)
    ax.set_xlabel('Value')
    ax.set_ylabel('Probability Density')
    ax.legend()
    plt.grid(True)
    plt.show()

    # --- 2. Quantification ---
    print("--- Quantitative Comparison ---")
    print(f"\n1. Direct Parameter Comparison:")
    print(f"   - Difference in Means (μ1 - μ2): {mean1 - mean2:.4f}")
    print(f"   - Difference in Standard Deviations (σ1 - σ2): {std1 - std2:.4f}")

    # Calculate KL Divergence in both directions
    try:
        kl_1_to_2 = kl_divergence_normal(params1, params2)
        kl_2_to_1 = kl_divergence_normal(params2, params1)

        print(f"\n2. Kullback-Leibler (KL) Divergence:")
        print("   (Measures the information lost when one distribution is used to approximate the other)")
        print(f"   - KL(Dist 1 || Dist 2): {kl_1_to_2:.4f}")
        print(f"   - KL(Dist 2 || Dist 1): {kl_2_to_1:.4f}")
        print("   Note: KL Divergence is not symmetric. A value of 0 means the distributions are identical.")

    except ValueError as e:
        print(f"\nCould not calculate KL Divergence: {e}")

def compare_normal_distributions(sample1, sample2):
    """
    Visualizes and statistically compares two samples from normal distributions.

    This function performs the following steps:
    1.  Creates overlapping histograms to visualize the distributions.
    2.  Generates side-by-side box plots to compare medians and spread.
    3.  Performs Levene's test to check for equality of variances.
    4.  Performs Welch's t-test to check for a significant difference in means.

    Args:
        sample1 (np.ndarray): The first sample dataset.
        sample2 (np.ndarray): The second sample dataset.
    """
    # --- 1. Visualization ---
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Overlapping Histograms
    ax1.hist(sample1, bins=30, density=True, alpha=0.7, label='Sample 1', color='skyblue')
    ax1.hist(sample2, bins=30, density=True, alpha=0.7, label='Sample 2', color='salmon')
    ax1.set_title('Overlapping Histograms of Sample Distributions')
    ax1.set_xlabel('Value')
    ax1.set_ylabel('Density')
    ax1.legend()

    # Side-by-side Box Plots
    ax2.boxplot([sample1, sample2], patch_artist=True,
                boxprops=dict(facecolor='lightgray', color='black'),
                medianprops=dict(color='black'),
                labels=['Sample 1', 'Sample 2'])
    ax2.set_title('Side-by-Side Box Plots')
    ax2.set_ylabel('Value')

    fig.suptitle('Visual Comparison of Two Samples', fontsize=16)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()

    # --- 2. Statistical Tests ---
    print("--- Statistical Test Results ---")

    # Levene's Test for Equality of Variances
    # This test is robust for data that is not perfectly normally distributed.
    # Null Hypothesis (H0): The variances of the two samples are equal.
    # Alternative Hypothesis (H1): The variances are not equal.
    levene_stat, levene_p_value = stats.levene(sample1, sample2)
    print(f"\n1. Levene's Test for Equality of Variances:")
    print(f"   - Test Statistic: {levene_stat:.4f}")
    print(f"   - p-value: {levene_p_value:.4f}")
    if levene_p_value < 0.05:
        print("   - Result: The p-value is less than 0.05. We reject the null hypothesis.")
        print("   - Conclusion: There is a statistically significant difference in the variances.")
    else:
        print("   - Result: The p-value is greater than or equal to 0.05. We fail to reject the null hypothesis.")
        print("   - Conclusion: There is no statistically significant difference in the variances.")

    # Welch's T-test for Equality of Means
    # We use Welch's t-test by setting equal_var=False. It does not assume equal population variance
    # and is generally recommended over Student's t-test.
    # Null Hypothesis (H0): The means of the two samples are equal.
    # Alternative Hypothesis (H1): The means are not equal.
    ttest_stat, ttest_p_value = stats.ttest_ind(sample1, sample2, equal_var=False)
    print(f"\n2. Welch's T-test for Equality of Means:")
    print(f"   - Test Statistic: {ttest_stat:.4f}")
    print(f"   - p-value: {ttest_p_value:.4f}")
    if ttest_p_value < 0.05:
        print("   - Result: The p-value is less than 0.05. We reject the null hypothesis.")
        print("   - Conclusion: There is a statistically significant difference in the means.")
    else:
        print("   - Result: The p-value is greater than or equal to 0.05. We fail to reject the null hypothesis.")
        print("   - Conclusion: There is no statistically significant difference in the means.")


def compare_experimental_to_smc(sample, theoretical_params, title='', verbose=False, plot=False, results_dir='./'):
    """
    Visualizes and statistically compares a sample to a theoretical normal distribution.

    This function performs the following steps:
    1.  Creates a histogram of the sample and overlays the theoretical PDF.
    2.  Generates a Q-Q plot to compare sample quantiles to theoretical quantiles.
    3.  Performs a one-sample t-test to compare the sample mean to the theoretical mean.
    4.  Performs a Chi-squared test to compare the sample variance to the theoretical variance.

    Args:
        sample (np.ndarray): The sample dataset.
        theoretical_params (tuple): A tuple containing the (mean, std_dev) of the
                                    theoretical normal distribution.
    """
    theoretical_mean, theoretical_std = theoretical_params
    theoretical_var = theoretical_std**2
    n = len(sample)
    
    if plot:
        # --- 1. Visualization ---
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

        # Histogram vs. Theoretical PDF
        ax1.hist(sample, bins=30, density=True, alpha=0.7, label='Sample Histogram', color='skyblue')
        x = np.linspace(min(sample), max(sample), 200)
        ax1.plot(x, stats.norm.pdf(x, theoretical_mean, theoretical_std), 'r-', lw=2, label='Theoretical PDF')
        ax1.set_title('Sample Histogram vs. Theoretical PDF')        
        ax1.set_xlabel('Value')
        ax1.set_ylabel('Density')
        ax1.legend()

        # Q-Q Plot
        stats.probplot(sample, dist="norm", sparams=theoretical_params, plot=ax2)
        ax2.set_title('Q-Q Plot against Theoretical Normal Distribution')
        # The default labels are "Theoretical quantiles" and "Ordered Values", which are fine.

        fig.suptitle(f'Visual Comparison of Experimental to SMC Distribution {title}', fontsize=16)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        #plt.show()
        plt.savefig(results_dir)

    # --- 2. Statistical Tests ---
    ttest_stat, ttest_p_value = stats.ttest_1samp(sample, theoretical_mean)
    if verbose:
        print("--- Statistical Test Results ---")
        # One-Sample T-test for the Mean
        # Null Hypothesis (H0): The mean of the sample is equal to the theoretical mean.
        print(f"\n1. One-Sample T-test (Comparing Means):")
        print(f"   - Sample Mean: {np.mean(sample):.4f}, Theoretical Mean: {theoretical_mean}")
        print(f"   - T-statistic: {ttest_stat:.4f}")
        print(f"   - p-value: {ttest_p_value:.4f}")
    if ttest_p_value < 0.05:
        means_different = True
        if verbose:
            print("   - Conclusion: Reject H0. The sample mean is significantly different from the theoretical mean.")
    else:
        means_different = False
        if verbose:
            print("   - Conclusion: Fail to reject H0. No significant difference between sample and theoretical means.")


    # Chi-squared Test for the Variance
    # Null Hypothesis (H0): The variance of the sample is equal to the theoretical variance.
    sample_var = np.var(sample, ddof=1) # Use ddof=1 for unbiased sample variance
    chi2_stat = (n - 1) * sample_var / theoretical_var
    df = n - 1 # degrees of freedom
    # Calculate two-tailed p-value
    p_from_cdf = stats.chi2.cdf(chi2_stat, df)
    # p_value is 2 * (area in the smaller tail)
    chi2_p_value = 2 * min(p_from_cdf, 1 - p_from_cdf)

    if verbose:
        print(f"\n2. Chi-Squared Test (Comparing Variances):")
        print(f"   - Sample Variance: {sample_var:.4f}, Theoretical Variance: {theoretical_var:.4f}")
        print(f"   - Chi-squared statistic: {chi2_stat:.4f}")
        print(f"   - p-value: {chi2_p_value:.4f}")
    if chi2_p_value < 0.05:
        std_different = True
        if verbose:
            print("   - Conclusion: Reject H0. The sample variance is significantly different from the theoretical variance.")
    else:
        std_different = False
        if verbose:
            print("   - Conclusion: Fail to reject H0. No significant difference between sample and theoretical variances.")
    
    return means_different, std_different


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
        for i in range(1000):
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
