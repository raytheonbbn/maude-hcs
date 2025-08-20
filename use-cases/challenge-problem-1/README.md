This directory contains the input HCS specifications for challenge problem 1 configs as well as the output SMC results.

The shadown YAML configs were converted to HCS Config specs included in this directory, `*-hcsconfig.json`.
We also include the generated maude files and the output smc results in json.

To re-run a use case and reproduce the results, generate then scheck as follows

```shell
maude-hcs --protocol=dns --run-args=case1_sim_config_cp1-hcsconfig.json --model=prob --filename=test generate
maude-hcs scheck --test=test --query=smc/latency.quatex --format json -j 0 -d0.5
```