It comprises 5 hidden channel types
  - Racebird (Obfs4)
  - Skyhook (Minio)
  - RaceTunnel (WebTunnel)
  - Mastodon + Destini 
  - Iodine 

The application is IRC 

There are a range of traffic generators driven by markov models.
The v2 markov models have two layers, a meta layer that determines what meta state we are in and transitions between these meta states,
and within each such meta state there is a markov model.
The v1 user models are single layer as in challenge problem 2
  -  FTP (v2 model)
  - MinIO (v2 model)
  - IRC (v2 model)
  - Gorilla chat (v2 model)
  - Mastodon (v1 model)
  - DNS (v1 model)

The network digram is attached