# Question / answer

## User model
Questions to @Paul Vines (TwoSix). The mastodon client user model described in raceboat looks like a timeline of events, as opposed to a parametrized markov process specified in @davidam2’s tgen. Is raceboat’s model a sampled timeline from the markov model or not necessarily? if not, will the fixed timeline be prespecified as a config time?

Answer from Aaron: we'll have to talk internally about that and get back to you

Joud/BBN: ok. the way I understand it is, for tgen client, we will be sampling from markov process so each iteration will be different random sample / timeline. the question is for raceboat client is it the same (ie raceboat supports markov process as input) or something else and if the latter what does that look like (certainly not a fixed timeline like it appears now)

# Libraries

 * Mastodon client used in raceboat transport: https://github.com/tst-race/mastodon-transport/blob/80c1b9a366f2b37b37c70f3082bfe67124bdf0dd/source/transport/MastodonClient.cpp
 * Mastodon client used in TGEN: python (TBD) but similar API
 * QUIC:  https://github.com/aiortc/aioquic
 * Iodine source code available at https://github.com/yarrick/iodine
 * Raceboat https://github.com/tst-race/raceboat
 * Destini https://github.com/tst-race/destini 
 * raceboat-destini example https://github.com/tst-race/decomposed-exemplars
 