Maude timed models of a simple round trip time
protocol (module RTT in rtt.maude) and a verion
(module WRTT in wrtt.maude) that carries hidden
information in the time stamp.

To run a simple instantiation of RTT 
terminalprompt> maude rtt.maude
Maude> rew {aO bO} .

To run a simple instantiation of WRTT 
terminalprompt> maude wrtt.maude
Maude> rew {aO bO} .

The file organization

time.maude --- the RTMaude time models
   includes  Time as Nat and Time as NzRat refinements
   float-time-inf.maude is the Time as Float refinement.
      should add this module to time.maude

rt-aux.maude  --- RTMaude infrastructure
   --- mte,timeEffect, time  management rules
   --- independent of choice of Time representation
   
rtt-aux.maude --- RTT specific data structures for
   --- for timestamps, and conversion operations 
   --- shared msg and attribute constructors
   
rtt.maude  --- the RTT protocol and instantiations
   to Time as Nat, NzRat, Float and Probablistic
wrtt.maude --- the WRTT protocol and instantiations
   to Time as Nat, NzRat, Float and Probablistic

The end of each instantiation has example rewrites.
In the probablistic case there is an example
of how to do repeated runs with different initial
values of the random counter object rCtr .
