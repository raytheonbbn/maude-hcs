# Probabilistic model

The scheduler is an important component of the probabilistic model (apmaude module).
The schedule is represented in mixfix as `{GlobalTime | ScheduledMessageList}`.

The scheduler performs the following starting with a configuration
containing an ActorConfig, Scheduler, and one or more ScheduledMsg objects
```
run(
    {0.0 | nil}
    < Alice : SendApp | ...>
    <...>
    [- log(float(random(counter) / 4294967296)) / 1.0, to Alice : start, 0]
    , limit)
```

 * reorganize the scheduled messages SMs `[..]` in the configuration to sort them by time
 * insert each SM into the scheduler; for example above `{0.0 | nil}  [- log(float(random(counter) / 4294967296)) / 1.0, to Alice : start, 0]` becomes `{0.0 | [0.599, to Alice : start, 0]}` 
 * run the which keeps stepping through
 * each step,
  * the closest SM in time is converted to an active message `{0.599, to Alice : start}` which is what triggers the rewrite rules
  * the scheduler global time is advanced to be the SM time `{5.9999659954903684e-1 | nil}`