# Question / answer

## User model
Questions to @Paul Vines (TwoSix). The mastodon client user model described in raceboat looks like a timeline of events, as opposed to a parametrized markov process specified in @davidam2’s tgen. Is raceboat’s model a sampled timeline from the markov model or not necessarily? if not, will the fixed timeline be prespecified as a config time?

Answer from Aaron: we'll have to talk internally about that and get back to you

Joud/BBN: ok. the way I understand it is, for tgen client, we will be sampling from markov process so each iteration will be different random sample / timeline. the question is for raceboat client is it the same (ie raceboat supports markov process as input) or something else and if the latter what does that look like (certainly not a fixed timeline like it appears now)

======

do we plan on a user model for Bob's Raceboat?  I think we said yes.  Does that mean Bob's periodically "getting" posts and images, even when it has no message from Alice?

Answer: yes it will have a model and the actions (whether they include scrolling) that's something we've been thinking about. Our existing Mastodon client can perform a bunch of actions beyond posting/fetching but we're looking at potentially paring down the list of actions we'll use for CP2. I don't have a final answer at the moment but this is something we're preparing to discuss at the raceboat workshop.

- how is Bob doing the fetching of messages via raceboat? is 
that according to some user model? or does Bob wait for the C2
msg to arrive before fetching via raceboat?

- what is the API between Bob and raceboat server? does bob
 get notified by RB server when there is data?

- Besides sending Ack on C2 channel does Bob send any other data?


- mastodon client actor: we have a client inside raceboat client/server
 and we have another client that is generating background traffic.
 do these clients use the same user model? when the user model is outside
 of raceboat actor, where does it live?

- user models: the user model in raceboat looks like a time series.
 Is this series precomputed or is it dynamic? 
 Is this series sampled from the same markov model used in TGEN? 
	if so, when does this sampling occur?

## Carolyn's

* Package from Alice to Raceboat
Is this just a bytestream/byte sequence or is there other
information?  

* What information does Alice get in response to a package
  submitted? When?

* What is configured in a Raceboat instance?  What paramters
are determined at link creation time? How is this specified?  
  The user id/credentials?
  Information about the other end of the link?
  Parameters for encoding/decoding?



* are the processes that queue content (fragmenting, encoding
  ..) effectively concurrent with the execution of the user model?
  Or does the user model ask someone for content when there is
  an action to be done.
 
* From raceboat slide 8 -- it appears that image retrieval is
  driven by user model and sent to Bob rather than Bob
  requesting retrieval once Alice sends the key and hashtag. Is
  that right? How do the raceboat instances coordinate on hash
  tags?
 
* Does the direction of arrows in the connection sequence slide (slide 4) reflect flow of messages to/from the users?
  
* User model
  Does the receiving raceboat use a user model to retrieve data?

*  Is there one user model representing sender and receiver 
held by both racebox instances? Or separage independent models?
(The example user model is an alternating sequence of
send/fetch actions suggesting it models both Alice and Bob.)

* Who uses the User Model?  The manager/coordinator or the
transport or ?

* If a package is fragmented do timeline send actions apply 
as if each resulting content is a new user request, or 
do all segments get send at once?


* Will CP2 use the by-need model or will the user model essentially  eliminate the need for a user actor?  

* In the email example in the raceboat paper, the action
  parameters are size and attachment if any. Emails usually
  have a sender and a receiver ... How are these determined?

* How are  actions/events specified and interpreted?

* The raceboat paper says that the encoding coomponnet is
responsible for providing requested content even when there
is no message to send.  How can it do this? Does it need
to interpret transport content specification?


The raceboat paper indicates the intended use is for control
plane communication. Why is CP2 using it for data plan
communication?


# Libraries

 * Mastodon client used in raceboat transport: https://github.com/tst-race/mastodon-transport/blob/80c1b9a366f2b37b37c70f3082bfe67124bdf0dd/source/transport/MastodonClient.cpp
 * Mastodon client used in TGEN: python Mastodon.py==2.0.1 https://mastodonpy.readthedocs.io/en/stable/ (see below details)
 * QUIC:  https://github.com/aiortc/aioquic
 * Iodine source code available at https://github.com/yarrick/iodine
 * Raceboat https://github.com/tst-race/raceboat
 * Destini https://github.com/tst-race/destini 
 * raceboat-destini example https://github.com/tst-race/decomposed-exemplars
 
 ## Mastodon python

The TGEN client uses the mastodon python package Mastodon.py==2.0.1

For posting a status we're using mastodon.status_post https://mastodonpy.readthedocs.io/en/stable/05_statuses.html#mastodon.Mastodon.media_post

For uploading an image(s)  we use mastodon.media_post https://mastodonpy.readthedocs.io/en/stable/05_statuses.html#mastodon.Mastodon.media_post
media_post returns media ids that map to images uploaded to the server. We provide the media id's to mastodon.status_post to make a post with images. Theres the option to provide text with the image in a post, but if we just provide it an empty string for the text, the post only contains images to resemble the mastodon transport in raceboat 