An Equational TrafficGenerator is composed of three
actors (equational user-model, equational
contentGenerator, and an observer) plus a counter
object rCtr(j) and an adversary object where
observations are collected.

The equational user-model and content generators are
obtained from the origian TGEN actors as follows
** rules are turned into equations 
    crl becomes ceq, => becomes =, 
** scheduled messages become active messages by 
adding the current time to the delay.
** configureations are reduced rather than rewritten.

This works becuase at each `rule' invokation, there
is exactly one message consumed and one message
produced (until the stopping time, when no message
is produced).

The observer actor is new. It simulates sending a
request and receiving a response by logging these
messages with suitable time stamps. The sending time
is the time the observer received the request, the
receiving time needs work to determine the
parameters and equation combining them.

The dns case is straight forward: one query gets one
response, so we need to model the time a query
bounces around the DNS network, and the effect of
possible drops.

The http case depends on the protocol and what we
can observer. In the Mastodon case, is there one
http connection per download, and one per
post/media? Then only one protocol request and
response are logged. If there is a new connection
for each http reqœuest/response, then each exchange
should be logged. In either case we need a model of
the time taken for each http request and http
response to happen and maybe extra connection setup
overhead.

The delays and messages to log are  parameters of the  observer traffic logging mechanism.

**********************************************
Files

ua-actor-eq.maude 
  -- equational version of user-model actor

dnsQgen-actor-eq.maude 
  -- equational version of the dnsQgen 
     (query generator) actor 
     
dnsObs-actor-eq.maude  
  --- observer pattern instantiated to DNS

dnsTgenEqConf.maude    
  ---  defines the top level function 
      produceDNSLog 
The arguments are: actor addresses, mamodel,
  start and stop times and initial rand counter 

produceDNSLog constructs the initial actor
configuration, then extracts the adversary object
from the reduced configuration.

All files have test examples.

TODO 
-- make the current adversary an argument to be
  extended by background traffic
-- Need to think about how to model multiple
  instances of a generator behavior

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
DNS message sequence pattern
     
Three cases 
(1) UM state maps to an action
-{T, actionR}-> um 
 if T < stopTime and curState is an action
    -{T,actionQ(ract)}-> cgen 
    -{T,req }-> obs 
     [logging]
     -{T+delay,ackMsg}-> cgen
     -{T+delay,actionR("ok")} -> um
 
(2) UM state maps to a wait
-{T, actionR}-> um -{T+waitTime,actionR}-> um 
 if T < stopTime and curState has type wait

(3) UM stop time is exceeded --- eq rewriting stops
-{T, actionR}("ok")-> um -> null
 if T >= stopTime
    
