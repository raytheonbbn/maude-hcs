This folder contains the Maude-HCS results from challenge problem 2 evaluation.

# Important assumptions and caveats

 * All scenarios are run *WITHOUT LOSS*
   * This is primarily because we did not yet implement a loss model that faithfully represents the high level of loss being used on the links (5% and 10%). 
   * This level of loss causes TCP performance to drop significantly (up to 10x), which means a simple loss delay model is insufficient
 * We focused on 2 performance and 2 scalability guarantees, specifically
   * Performance: Latency, and goodput
   * Scalability: operating duration, and number of exfil files 
 * For scalability, we only include the results for C.2, C.8, and MA.1 profiles. 
   * This is because these were the ones we were able to test and validate in limited time we had. We do have the rest of the profiles implemented but not validated.
   * Regarding C.8: we measure the number of HTTPs connections post NAT (the majority of these are created by raceboat); we weren't able to verify this matches what T&E is measuring in zeek 
 * In terms of guarantees, 
   * Maude-HCS provides statistical guarantees of the form *the expected value of a measure is within a range $[\hat{v}-\delta/2, \hat{v}+\delta/2]$ with confidence $(1-\alpha)$}, given desired confidence parameters $\alpha$ and $\delta$*. We refer to $\delta$ as the radius and we set $\alpha$ to 0.05 (95% confidence).  
   * Since T&E requested CDFs also (not something we support natively), we extended SMC to generate the samples and we produced CDFs for all scenarios except scenarios 3, 6, 9, 12 
     * Generating samples for CDFs requires serially executing the N samples (one thread) which is significantly slower and takes a very long time for scenario 3, 6, 9, 12 given they use 48 tgens each 
     * For scenario 6, we have a coarse CDF estimate using only 30 samples 

# Interpreting the results
Folder `results-measures` contains the statistical estimates per scenario.
Each scenario file contains 8 query results corresponsing to the 2 performance properties, plus the 6 scalability properties (C.2, C.8, MA.1 for both op duration and num files).
Each query result is annotated with what it is measuring, for example
```json
        {
          "mean": 190.52147725541835,
          "std": 16.86834431252156,
          "radius": 1.916555513011477,
          "nsims": 300,
          "discarded": 0,
          "measure": "eval E[Latency()] with delta = 2 ;",
          "PoD": 0.0
        }
```
This estimate is for the expecetd value of latency `E[latency]` (as indicated in `measure`).

We also include the probability of detect for the scalability estimated: this is computed as (1 - `discarded`/(`discarded`+`nsims`)),
where `discarded` is the number of sims discarded by SMC because of no detection.

This query result from scenario 5 on the other hand is for `E[ExfilFilesC8()]` whcih is the C.8 num exfil files
```json
        {
          "mean": 4.956521739130435,
          "std": 0.20851441405708124,
          "radius": 0.0901683942566991,
          "nsims": 23,
          "discarded": 277,
          "measure": "eval E[ExfilFilesC8()];",
          "PoD": 0.07
        }
```

Folder `results-cdf` contains the CDF plots as well as the raw samples for each of the measures in the `*.dat` files.
Each row in the .dat files corresponds to a sample
The 8 columns in each row correspond to
```shell
    col == 0  "latency.pdf"
    col == 1  "goodput.pdf"
    col == 2  "exfil_c2.pdf"
    col == 3  "exfil_c8.pdf"
    col == 4  "exfil_ma1.pdf"
    col == 5  "op_c2.pdf"
    col == 6  "op_c8.pdf"
    col == 7  "op_ma1.pdf"
```

Folder `results-initconf` contains the initial configuration specification used for the scenarios for statistical model checking.

# Source 

The source code used for generating these results is on branch `cp2.eval` on the public maude-hcs repository. 
    https://github.com/raytheonbbn/maude-hcs/tree/cp2.eval