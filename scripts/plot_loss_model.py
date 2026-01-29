import matplotlib.pyplot as plt
import numpy as np


def parse_data(raw_data):
    """
    Parses the raw table data.
    Expected format: Size | ConnAvg | ConnMin | ConnMax | TransAvg | TransMin | TransMax
    Returns lists of sizes, averages, mins, and maxs for Total Time.
    """
    sizes = []
    means = []
    mins = []
    maxs = []

    # split into lines and filter out empty lines
    lines = [line.strip() for line in raw_data.strip().split('\n') if line.strip()]

    for line in lines:
        # Skip header lines if they are included by accident (checking for numeric start)
        if not line[0].isdigit():
            continue

        parts = line.split('|')
        try:
            # Column 0: Size
            size = float(parts[0].strip())

            # Connection Times
            conn_avg = float(parts[1].strip())
            conn_min = float(parts[2].strip())
            conn_max = float(parts[3].strip())

            # Transfer Times
            trans_avg = float(parts[4].strip())
            trans_min = float(parts[5].strip())
            trans_max = float(parts[6].strip())

            # Calculate Totals
            total_mean = conn_avg + trans_avg
            total_min = conn_min + trans_min
            total_max = conn_max + trans_max

            sizes.append(size)
            means.append(total_mean)
            mins.append(total_min)
            maxs.append(total_max)

        except (ValueError, IndexError):
            continue

    return sizes, means, mins, maxs


def fit_and_plot(ax, sizes, means, mins, maxs, loss_pct, rtt_ms, color):
    """
    Fits the data to the model: Latency = S + f(Size, Loss, RTT)
    Where f is linear: K * Size * RTT * sqrt(Loss)
    Plots both the error bar data and the fitted line.
    """
    sizes_arr = np.array(sizes)
    means_arr = np.array(means)

    # Linear Fit (y = mx + c)
    # Slope (m) represents the transfer rate factor
    # Intercept (c) represents the Setup Time (S)
    slope, intercept = np.polyfit(sizes_arr, means_arr, 1)

    fit_values = slope * sizes_arr + intercept

    # Plot Data with Error Bars
    # Calculate asymmetric error bars (Average - Min, Max - Average)
    yerr_low = [m - low for m, low in zip(means, mins)]
    yerr_high = [high - m for m, high in zip(means, maxs)]
    y_errors = [yerr_low, yerr_high]

    label_base = f'{loss_pct}% Loss, {rtt_ms}ms RTT'
    ax.errorbar(sizes, means, yerr=y_errors, fmt='o', color=color,
                linewidth=2, capsize=4, label=f'{label_base} (Data)')

    # Prepare Fit Label
    # We check for loss > 0 to avoid division by zero in the K calculation
    if loss_pct > 0:
        # Convert parameters to standard units for calculation
        loss_prob = loss_pct / 100.0
        rtt_sec = rtt_ms / 1000.0
        # Derive K from the slope based on the model: m = K * RTT * sqrt(Loss)
        k_const = slope / (rtt_sec * np.sqrt(loss_prob))
        fit_label = f'Fit: S={intercept:.2f}s, K={k_const:.2e}'
    else:
        # For 0% loss, the sqrt(loss) in denominator is invalid for K calculation
        # The slope here is purely 1/Bandwidth
        fit_label = f'Fit: S={intercept:.2f}s, Slope={slope:.2e}'

    # Plot Fitted Line
    ax.plot(sizes_arr, fit_values, linestyle='--', color=color, linewidth=1.5,
            label=fit_label)


# --- Data Series 1: 5% Loss, 50ms RTT ---
data_series_1 = """
500000     | 0.528462  | 0.208766  | 3.258718  | 2.277270  | 0.300678  | 7.183811
600000     | 0.424663  | 0.209109  | 3.253078  | 3.050102  | 0.300832  | 8.390808
700000     | 0.511165  | 0.209165  | 1.637297  | 3.363726  | 0.300853  | 10.097298
800000     | 0.369995  | 0.209435  | 1.236449  | 5.574743  | 0.642134  | 12.575932
900000     | 0.372109  | 0.208823  | 1.256599  | 5.637814  | 0.544456  | 15.233924
1000000    | 0.315107  | 0.209455  | 1.265036  | 6.187660  | 0.702500  | 13.966508
1100000    | 0.353343  | 0.208967  | 1.236344  | 6.838564  | 0.602074  | 16.184980
1200000    | 0.381282  | 0.209223  | 1.259289  | 8.130028  | 1.103281  | 15.286560
1300000    | 0.342807  | 0.208802  | 1.221094  | 10.627144 | 1.006344  | 16.951885
1400000    | 0.414433  | 0.209395  | 1.230295  | 7.921262  | 3.280082  | 14.362024
1500000    | 0.272031  | 0.209417  | 0.521877  | 13.282191 | 3.959594  | 19.441058
1600000    | 0.209820  | 0.209536  | 0.210171  | 14.292498 | 3.352420  | 21.536386
1700000    | 0.270634  | 0.209472  | 0.513241  | 16.719436 | 4.714633  | 23.093464
1800000    | 0.209861  | 0.209613  | 0.210145  | 17.568318 | 9.275167  | 23.148180
1900000    | 0.421556  | 0.209996  | 1.267050  | 17.212876 | 9.779830  | 21.092812
2000000    | 0.209782  | 0.209315  | 0.210422  | 17.953053 | 10.766059 | 27.460093
"""

# --- Data Series 2: 2.5% Loss, 50ms RTT ---
data_series_2 = """
500000     | 0.209928  | 0.209054  | 0.214003  | 0.952339  | 0.300796  | 4.153672 
600000     | 0.313843  | 0.209068  | 1.267323  | 1.283234  | 0.300838  | 4.110187 
700000     | 0.240389  | 0.209268  | 0.817213  | 1.923893  | 0.541947  | 5.358894 
800000     | 0.224899  | 0.208991  | 0.511561  | 2.203607  | 0.542214  | 7.477885 
900000     | 0.224844  | 0.209001  | 0.511416  | 2.656846  | 0.401533  | 7.168776 
1000000    | 0.261923  | 0.208594  | 1.251247  | 2.181247  | 0.401229  | 8.286826 
1100000    | 0.250826  | 0.208924  | 0.722828  | 4.095832  | 0.543311  | 10.837101
1200000    | 0.260605  | 0.209081  | 1.221075  | 3.822716  | 0.602860  | 12.190362
1300000    | 0.326378  | 0.209057  | 1.236153  | 4.559793  | 0.542536  | 10.414380
1400000    | 0.345066  | 0.209248  | 1.254232  | 5.138361  | 0.601830  | 10.533280
1500000    | 0.328728  | 0.209373  | 1.266046  | 5.588239  | 0.605943  | 12.800918
1600000    | 0.240281  | 0.208253  | 0.518574  | 5.460656  | 0.643491  | 13.341664
1700000    | 0.240377  | 0.209058  | 0.516293  | 6.158242  | 0.602756  | 11.206971
1800000    | 0.209828  | 0.208928  | 0.211024  | 6.267335  | 0.602360  | 12.485200
1900000    | 0.209936  | 0.209051  | 0.211073  | 6.994559  | 1.004572  | 12.633747
2000000    | 0.260236  | 0.208419  | 1.220845  | 8.108043  | 0.602185  | 17.971070
"""

# --- Data Series 3: 0% Loss, 50ms RTT ---
data_series_3 = """
500000     | 0.209968  | 0.209104  | 0.213608  | 0.300995  | 0.300583  | 0.301989 
600000     | 0.210126  | 0.209130  | 0.211495  | 0.314529  | 0.300659  | 0.601408 
700000     | 0.209730  | 0.208589  | 0.210940  | 0.519405  | 0.300757  | 0.902892 
800000     | 0.210005  | 0.209206  | 0.211392  | 0.522174  | 0.400764  | 0.543301 
900000     | 0.209817  | 0.208548  | 0.211254  | 0.594443  | 0.400924  | 1.403532 
1000000    | 0.209926  | 0.208770  | 0.211500  | 0.638091  | 0.401222  | 1.605224 
1100000    | 0.209925  | 0.208876  | 0.210917  | 0.677067  | 0.401660  | 1.806350 
1200000    | 0.209950  | 0.209145  | 0.211320  | 0.587416  | 0.400981  | 0.802950 
1300000    | 0.209769  | 0.208835  | 0.211655  | 0.579243  | 0.401101  | 0.902398 
1400000    | 0.210017  | 0.208992  | 0.211594  | 0.623637  | 0.501641  | 1.003342 
1500000    | 0.210054  | 0.209076  | 0.212411  | 0.749118  | 0.502485  | 3.408665 
1600000    | 0.210126  | 0.208471  | 0.213596  | 0.645516  | 0.502728  | 1.002223 
1700000    | 0.209885  | 0.208871  | 0.211256  | 0.737674  | 0.542033  | 3.009598 
1800000    | 0.210182  | 0.209128  | 0.212196  | 0.654896  | 0.501938  | 1.004260 
1900000    | 0.209770  | 0.208832  | 0.211289  | 0.741310  | 0.543035  | 2.608968 
2000000    | 0.210032  | 0.209243  | 0.211750  | 0.658390  | 0.602261  | 1.003601 
"""

# Plotting Setup
fig, ax = plt.subplots(figsize=(10, 6))

# Process and Plot Series 1
sizes1, means1, mins1, maxs1 = parse_data(data_series_1)
fit_and_plot(ax, sizes1, means1, mins1, maxs1, loss_pct=5, rtt_ms=50, color='tab:blue')

# Process and Plot Series 2
sizes2, means2, mins2, maxs2 = parse_data(data_series_2)
fit_and_plot(ax, sizes2, means2, mins2, maxs2, loss_pct=2.5, rtt_ms=50, color='tab:orange')

# Process and Plot Series 3
sizes3, means3, mins3, maxs3 = parse_data(data_series_3)
fit_and_plot(ax, sizes3, means3, mins3, maxs3, loss_pct=0, rtt_ms=50, color='tab:green')

# --- Formatting ---
ax.set_title('File Size vs. Total Transfer Time (Data + Model Fit)', fontsize=14)
ax.set_xlabel('File Size (Bytes)', fontsize=12)
ax.set_ylabel('Total Time (Seconds)', fontsize=12)
ax.grid(True, linestyle='--', alpha=0.7)
ax.legend(fontsize=10)

# Format x-axis to be in scientific notation (e.g., 1e5)
ax.ticklabel_format(style='sci', axis='x', scilimits=(0, 0))

plt.tight_layout()
plt.show()