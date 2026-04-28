PWND-067-irc_raceboat_translation


The bidir raceboat pattern
 (a) has a two actor interface
     the CMSender receives app data, encodes and sends it
     the CMReceiver receives encoded data, decodes and
         sends to the connected app
   Thus for a app to connect directly, it needs to 
   deal with different actors to send to/receive from
 (b) the app data type need not be the same as the
    typed the CMs expect.  Someone needs to deal with
    the conversion (marshalling/unmarschalling)

To deal with the above an interface actor is defined
that does any needed data conversion and presents a
unique connection point for the app actors. This also
means that the same raceboat channels can be used by
different apps (with different message data types)
with out change.  Just define a suitable interface
actor type.

A simple interface actor knows its app endpoint and the
corresponding raceboate sender and receiver. It also
knows how to convert app data to raceboat data and vv.
It assumes each app message content can be transmitted
as one byteseq entity. A more complex interface might
break app data into chunks and and reassemble. We start
with a concrete interface for irc over a mastodon
channel. Next step is to make an nterface module
parameterized by the conversion functions.

 
In the case of raceboatMastodon here are the
changes to make it app agnostic:

In rb-cm-sender-mas.maude
rl [rbc-rcv-file] :  
modify the received message content to be sort Byteseq
and omit the conversion to Byteseq in the rule consequence.

In rb-cm-receiver-mas-aux.maude
modify the function rcvDecR to omit the conversion of assembled byteseq (efile) from byteseq to app data (IrcMsg), just send the assembled efile.
[This function is called by the rule crl [rbs-rcv-decR] in rb-cm-receiver-mas.maude]

The basic pattern for constructing a configuration with
app endpoints A,B communicating over a raceboat channel
(assuming A,B with one connection each)

*** endpoint A
mkAppA(appAAddr,ifAAddr,<other appA params>)
mkIface(ifAAddr,appAAddr,rbASndAddr,rbARcvAddr)
mkRaceboatEndpoint(rbASndAddr,rbARcvAddr,
                   umASndAddr,umARcvAddr,
                   <other rb paraneters> )

*** endpoint B
mkAppB(appBAddr,ifBAddr,<other appB params>)
mkIface(ifBAddr,appBAddr,rbBSndAddr,rbBRcvAddr)
mkRaceboatEndpoint(rbBSndAddr,rbBRcvAddr,
                   umBSndAddr,umBRcvAddr,
                   <other rb paraneters> )

