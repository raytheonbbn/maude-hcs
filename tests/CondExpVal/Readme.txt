Here is a much simplified version of the weird network
where there are cases when latency is undefined and
smc does not terminate.


actor.maude,  sampler.maude, and apmaude.maude are the
core modules from the ETH DNS model -- defining actors,
the scheduler, and that required SMC functions.

cond-ev-test.maude - defines the module COND-EV 
There are three actor classes: Sender, Receiver, and Monitor 

There is and an initial state constructor 

 initState(alice,bob,mon,fsz,max,freq,dly,nse,drp)

alice is the sender address
bob is the receiver address
mon is the monitor address
fsz is the file sized -- the number of packets to send
   before sending eof
max is the max number of packets to send -
    - alice may continue sending background traffic after the
    - file is transmitted
freq is the packet sending rate per second
dly is the latency
drp is the loss probablility (0.0 means no drops)
nse is the bound on latency/loss noise.
 
 
To test, define an initstate, then

[shellprompt} maude cond-ev-test
Maude> rew run({0.0 | nil} initstate, limit) .

Two initial states are provided:
iSmall -- file size 10, max packets 15, frequency 20
          dly .04, nse .001
iBig -- like iSmall except file size 100 max packets 150
    (not really useful)
See example commands after the eof.
      
smc.maude  includes COND-EV and APMAUDE and defines
the functions used by the latency quatex formula defined in
latency.quatex     

smc.maude contains (after eof) two smc commands illustrating
(a) successful computation with no loss, and non-termination
in the presence of loss.

