# MinIO Tgen Actor Implementation Walkthrough

The MinIO tgen actor is now implemented and wired with the V2 Markov model to produce S3 API calls on the network based on simulated user actions.

## 1. MinIO MAModel-V2 Generation

First, we ran the V2 converter on the MinIO `config.json` to generate the new Maude model:
- **[minio-mamodel-v2.maude](file:///Users/dcirimel/pwnd2/maude-hcs/maude_hcs/lib/tgen/maude/minio/minio-mamodel-v2.maude)**: This file contains the 2-level hierarchy of modes (`browse`, `upload`, `download`, `idle`) and specific actions (e.g., `browse_list`, `upload_store`, `download_retr`), along with transition probabilities and burst delay parameters.

## 2. MinIO Tgen Actor

The core logic of the new traffic generation actor was implemented in **[minioTgen-actor.maude](file:///Users/dcirimel/pwnd2/maude-hcs/maude_hcs/lib/tgen/maude/minio/minioTgen-actor.maude)**.

> [!TIP]
> **Design Pattern Reuse**
> Rather than creating a new set of network messages and servers, we reused the existing S3 protocol stack from `lib/s3` and `lib/skyhook`. The `MinioTgen` actor directly delegates network calls to the `S3SdkClient`.

The actor implements:
1. `rcvMinioAction`: Receives the `actionQ` message from the UM-V2 actor.
2. `dispatchAction`: Maps MinIO actions to corresponding S3 HTTP interactions:
   - `browse_list`, `browse_stat`, `browse_cd` → `S3GetObjReq`
   - `upload_store` → `S3PutObjReq`
   - `upload_appe` → **Combined `S3GetObjReq` + `S3PutObjReq`**
   - `download_retr` → `S3GetObjReq`
   - `*_noop` → immediate local `actionR("ok")`
3. Response handlers: Listens for `S3GetObjRes`, `S3PutObjRes`, `S3GetObjErr` and properly routes `actionR("ok")` back to the UM-V2 model, advancing the simulation.

## 3. Test Scenario & Validation

We wrote a test scenario in **[test-minio-tgen-v2.maude](file:///Users/dcirimel/pwnd2/maude-hcs/maude_hcs/lib/tgen/maude/minio/test-minio-tgen-v2.maude)** to validate the entire workflow:

```maude
  --- UM-V2 Actor
  op umAct : -> Actor .
  eq umAct = mkTgenUMV2Actor(minioUMAddr, "minio", minioTGAddr) .

  --- MinIO Tgen Actor
  op minioTGenA : -> Actor .
  eq minioTGenA = mkMinioTgenA(minioTGAddr, s3ClientAddr, "tgen") .

  --- S3 SDK Client Actor (S3 abstract -> HTTP)
  op s3ClientA : -> Actor .
  eq s3ClientA = makeS3Client(s3ClientAddr, s3ServerAddr) .

  --- S3 HTTP Server Mock
  op s3ServerA : -> Actor .
  eq s3ServerA = < s3ServerAddr : AwsS3HttpServer | s3DataMap: ( ... pre-seeded ... ) > .
```

We ran the test simulation and observed the expected Maude transitions. For example, during a `browse_stat` action, the following correctly cascades across actors:
1. UM-V2 sends `actionQ("type" |-> js("browse_stat"))`
2. MinioTgen receives `actionQ` and sends `S3GetObjReq` to SDK
3. SDK sends HTTP `GET /tgen/stat-8` to AWS Mock
4. AWS Mock responds with HTTP 404 (or 200 depending on seed data)
5. SDK converts response to `S3GetObjErr` (or `S3GetObjRes`) back to MinioTgen
6. MinioTgen responds to UM-V2 with `actionR("ok")`

> [!NOTE]
> Like the Python MinIO client behavior (which silently traps exceptions in `fn_map`), the MinIO Tgen actor also sends an `actionR("ok")` back to the UM-V2 even when it receives a 404 from the S3 mock, allowing the traffic generation sequence to keep going seamlessly.
