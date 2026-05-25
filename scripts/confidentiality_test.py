import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import ks_2samp

# ==========================================
# 1. Generate Test Dataset (H0 and H1)
# ==========================================
np.random.seed(42)

total_bins = 60
switch_point = 30 # Time step where H1 (HCS) begins

# We use Poisson distributions to simulate count data (e.g., DNS queries per bin)
# H0 (Baseline): mean of 5 queries per bin
# H1 (HCS Active): mean of 10 queries per bin
data_h0 = np.random.poisson(lam=5, size=switch_point)
data_h1 = np.random.poisson(lam=10, size=(total_bins - switch_point))

# Combine to create the observed time series x_t
x = np.concatenate([data_h0, data_h1])

# Generate a large, clean baseline pool to represent F_0(z)
baseline_pool = np.random.poisson(lam=5, size=1000)

# ==========================================
# 2. Algorithm Parameters
# ==========================================
m = 10     # Window size (number of recent bins)
k = 0.2    # Expected KS distance under H0 (drift parameter)
h = 1.0    # Evidence threshold for alarming

# Arrays to store step-by-step metrics for plotting
D_scores = np.zeros(total_bins)
S_scores = np.zeros(total_bins)
alarms = []

# ==========================================
# 3. Apply KS + CUSUM Steps
# ==========================================
S_t_minus_1 = 0.0

for t in range(total_bins):
    if t < m - 1:
        # Not enough data to fill the first window
        D_scores[t] = 0
        S_scores[t] = 0
        continue
        
    # Extract the sliding window W_t of the most recent m bins
    W_t = x[t - m + 1 : t + 1]
    
    # Step 1: Window deviation via KS distance
    # Compare empirical window W_t to the baseline pool (representing F_0)
    ks_stat, _ = ks_2samp(W_t, baseline_pool)
    D_t = ks_stat 
    
    # Step 2: Center the deviation
    Z_t = D_t - k
    
    # Step 3: Accumulate evidence
    S_t = max(0, S_t_minus_1 + Z_t)
    
    # Store metrics
    D_scores[t] = D_t
    S_scores[t] = S_t
    
    # Step 4: Alarm rule
    if S_t >= h and len(alarms) == 0:
        # Record the time t of the first alarm
        alarms.append(t)
        print(f"ALARM triggered at bin t={t} (S_t = {S_t:.3f} >= {h})")
        
    # Update S_{t-1} for the next iteration
    S_t_minus_1 = S_t

# ==========================================
# 4. Plot the Results (Replicating the Slide)
# ==========================================
fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

# Plot 1: Observed Feature Values x_t
colors = ['#1f77b4' if i < switch_point else '#d62728' for i in range(total_bins)]
axs[0].bar(range(total_bins), x, color=colors)
axs[0].set_ylabel('$x_t$ (Queries)')
axs[0].set_title('Observed Feature Values (Blue: H0, Red: H1)')
axs[0].axvline(x=switch_point, color='gray', linestyle='--', label='H1 Starts')

# Plot 2: KS Distance D_t
axs[1].plot(range(total_bins), D_scores, color='#2ca02c')
axs[1].axhline(y=k, color='gray', linestyle='--', label=f'Expected k={k}')
axs[1].set_ylabel('$D_t$ (KS Dist)')
axs[1].legend(loc='upper left')

# Plot 3: Cumulative Sum S_t
axs[2].plot(range(total_bins), S_scores, color='#9467bd')
axs[2].axhline(y=h, color='red', linestyle='--', label=f'Threshold h={h}')
if alarms:
    axs[2].scatter(alarms[0], S_scores[alarms[0]], color='red', zorder=5, label='Alarm Triggered')
axs[2].set_ylabel('$S_t$ (CUSUM)')
axs[2].set_xlabel('Time $t$ (bins)')
axs[2].legend(loc='upper left')

plt.tight_layout()
plt.show()
