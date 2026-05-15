Changes to irc modules  to support
T&E style message sending schedule
(also skyhook/skyhook_prob and 
a new directory in cp3-Tests)

Changed modules were copied, 
    <file>.maude >> <file> copy.maude  
before editing for easy comparison. 
Copies should be deleted before merging.

---------------------------
in irc/common/irc_names
sload ../../../deps/dns_formalization/Maude/common/actor
mod IRC_NAMES is
  pr ACTOR-MODEL .
  pr ADDRESS .

NO CHANGE
---------------------------
in irc/_irc_aux

 sload common/irc_name.maude
 mod IRC_AUX is
   pr CONVERSION .
   pr IRC_NAMES .

added defn of ircTextSize
as text has been abstracted 
and
replaced length(TEXT:String) 
by
ircTextSize(TEXT:String) in 
PrivMsgReq/Res cases of getSize

Test:
red getSize(PrivMsgReq(makeIrcChannelName("ab"), makeIrcUserName(nullAddr), "Alice:1:222"))  == 333 .
---------------------------
added irc/common/irs-msg-model

mod IRC-MSG-MODEL is
   pr CONVERSION .

defines the schedule datatype and
text representation function
 ---------------------------
in irc/common/_aux

sload ./irc_name
sload ../../common/maude/_aux
sload ../_irc_aux
sload ./app_chat >> irc-msg-model

mod IRC_NODE is
**** pr IRC_NAMES .
  pr CP2_SORTS .
  pr IRC_AUX .
****  pr APP_CHATS .
  inc IRC-MSG-MODEL .
  
added attributes and client constructor  for handling irc msg model
red mkIrcClient(nullAddr,nullAddr,"al",nilIMD) .
red mkIrcClient(nullAddr,nullAddr,"al",sampleDMLe ) .

 ---------------------------
in irc/irc_prob

 sload ./common/irc_name
 sload ./common/_aux
**** sload ./common/app_chat
 sload ./common/irc-msg-model
 sload ../common/maude/cp2-interfaces
 sload ../common/maude/delay-drop-x

 mod IRC is
   pr IRC_NODE .
   pr IRC_AUX .
   pr CP2-COMMON .
  inc IRC-MSG-MODEL .

replace rules
rl [irc-client-start]:
rl [irc-client-handle-outgoing-chat]:
 by single rule
crl [irc-client-send-time]:

IRC client receives ircMsgSendTime sends message
specified by the first element of the msgSched list. 
If there are more elements, send self ircMsgSendTime
delayed by the delay of the first(rest(msgSched)).

The rule uses supporting functions
genPrivMsgReq
ircSendMsg
setIrcMsgTimer
 
also delayMsgs >> delayMsgsX 

 ---------------------------
in irc/test_prob_irc -- modified to use new client
constructor and initial messages


-----------------------------------
in skyhook/_skyhook_aux.maude
added AH constructor mkSkyhookAH ---makeSkyhookAH with
a final argument used to set the attribute openObjects:

------------------------------------
in cp3-Tests
added Skyhook1/test-irc-skyhook-2room.maude
this is a copy of Skyhook/test-irc-skyhook-2room.maude
modified to use ircClients with message schedules.
The file contains two scenarios: 
  initConfig1 (two clients, two rooms, 
               both cliebts join both rooms); 
     and 
 initConfig - adds a third client that only joins one room. 

Alice has 5 messages to send,
Bob and Eve have 4 messages each.

test-irc-skyhook-2room.maude uses my version of the
ircMonitor -- it logs the actual message (along with the
size and identifier).

test-irc-skyhook-2room-smc.maude 
uses  Christophe's original ircMonitor messageTimeStamp
structure.   It also adds two attributes for
configuration parameters that Minyoung mentioned:
  ircClients: --- the set of irc client addresses
   for initConfig ---- (ircaAddr ;; ircbAddr ;; irceAddr), 
  roomClients: --- a set of pairs rm(room,addrs)
    where room is the string naming the room
    and addrs is the set of addresses of irc clients
    that join the room
  for initConfig this is    
    rm("#room1", ircaAddr ;; ircbAddr) 
    rm("#room2", ircaAddr ;; ircbAddr ;; irceAddr)

Probably we should delete cp3-Tests/Skyhook since it
won't work any more.    