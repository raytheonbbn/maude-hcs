import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

def compare_experimental_to_smc(sample, theoretical_params, verbose=False, plot=False):
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

        fig.suptitle('Visual Comparison of Experimental to SMC Distribution', fontsize=16)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.show()

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


if __name__ == '__main__':
    # Set the seed for reproducibility.
    np.random.seed(42)

    # --- Scenario 1: Sample is drawn from a distribution very similar to the theoretical one ---
    print("--- SCENARIO 1: Comparing samples to a similar theoretical distribution ---")    
    # TODO replace this with experimental samples (testing for now)
    sample1 = np.random.normal(loc=90.5, scale=15.5, size=500)
    # Define the theoretical distribution it should be similar to
    theoretical1 = (90, 15) # (mean, std_dev)
    means_different, std_different = compare_experimental_to_smc(sample1, theoretical1)
    assert not means_different and not std_different, 'expecting same dist'
    print("\n" + "="*80 + "\n")

    # --- Scenario 2: Sample is drawn from a distribution clearly different from the theoretical one ---
    print("--- SCENARIO 2: Comparing a sample to a different theoretical distribution ---")
    # Generate a sample with a different mean and standard deviation
    sample2 = np.random.normal(loc=110, scale=25, size=500)
    means_different, std_different = compare_experimental_to_smc(sample2, theoretical1)
    assert means_different and std_different, 'expecting different dist'
