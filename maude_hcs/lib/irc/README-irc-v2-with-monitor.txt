The update to v2 user models for irc involved the following changes.

irc_prob-v2.maude  --- the irc client adapted to be driven by a user model
irc-mamodel-v2.maude  --- example user model translated to maude

The following fix bugs in Christophe's interface/monitor modules
irc-byteseq-interface.maude  --- an irc interface actor that converts
   IrcMsg content to/from ByteSeq and logs messages in the IrcMonitor
ircMonitor.maude  ---  the IrcMonitor actor and auxiliary functions

test-irc-v2-with-monitor.maude  --- a test scenario with empty tunnel
   i.e. the client and server interfaces just talk to each other
   illustrates scenario construction using the v2 user model, new
   versions of interface and monitor actors.
   
      
