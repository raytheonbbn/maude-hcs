# Challenge problem 1

To compare SMC results produced by maude-hcs to the T&E experimental results, run

```
python compare_normal_dists.py cp1demodata/results-final/ cp1demodata/pwnd_cp1_data/ results/comparison2/ > results/comparison2/log.txt
```

The first argument is the directory with the statistical guarantees produced by SMC

The second argument is the directory with the raw samples produced by the T&E team

The third argument is the results directory where the outputs will be stored

This comparison assesses how predictive the model is of the real testbed (simulation / emulation) for performance guarantees