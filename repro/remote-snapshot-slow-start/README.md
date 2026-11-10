# Slow searchable snapshot startup

One OpenSearch node with `cluster_manager,data,warm` roles, MinIO and Toxiproxy. The script creates 1000 one-shard indices, snapshots them, restores them as `remote_snapshot`, adds 200 ms downstream S3 latency and times a restart until green with all 1000 shards started. It uses public images and needs no OpenSearch build or host network commands.

Requires Docker Compose v2, curl, a POSIX shell, 8 GiB Docker RAM and 15 GiB free disk. The Docker VM needs `vm.max_map_count` of at least 262144. If necessary, set it with `docker run --rm --privileged alpine:3.20 sysctl -w vm.max_map_count=262144`.

Start a fresh, disposable Compose project with the official `opensearchproject/opensearch:3.9.0` image:

```sh
git clone --depth 1 --filter=blob:none --sparse --branch repro-remote-snapshot-slow-start https://github.com/moleus/OpenSearch.git snapshot-repro
git -C snapshot-repro sparse-checkout set repro/remote-snapshot-slow-start
cd snapshot-repro/repro/remote-snapshot-slow-start
./repro.sh setup
./repro.sh restart
```

Switch only the OpenSearch image to the public fixed tag and digest in [fixed-image.txt](fixed-image.txt), then repeat:

```sh
WARM_IMAGE="$(cat fixed-image.txt)" ./repro.sh restart
```

[GitHub Actions](https://github.com/moleus/OpenSearch/actions/runs/42796520647) built and pushed `ghcr.io/moleus/opensearch:3.9.0-pr23563-5d346ded` for AMD64 and ARM64. Anonymous manifest retrieval and pull by tag+digest succeeded. The [Dockerfile](Dockerfile) builds the 3.9.0 release source at `4ee42a94e87f66fbf1e62a9871b1b87f91e02472` with [fix.patch](fix.patch), the complete production-code diff of [PR #23563](https://github.com/opensearch-project/OpenSearch/pull/23563) at `5d346deda1ec71d8293ea5faa0ed722c8a83e39f`. It replaces only the release server jar. This is a 3.9.0 backport of the PR changes. The helper installs and preserves the release S3 plugin for the stock image and sets public test credentials for both variants.

The script prints `start_to_green_s`. The timer begins immediately before starting the replacement container and includes JVM startup. Image pulling and node stopping happen before it. Green is polled once per second; the script then verifies that all 1000 restored shards are started. Repeated restarts preserve the warm data/cache volumes.

## Lab observations

Linux AMD64, 2 full-share vCPU, 12 GiB RAM, four concurrent initial recoveries, snapshot pool max 5, 1000 searchable snapshot shards and 200 ms downstream latency without jitter. One restart per image. The fixed run restores the stock run's snapshot and warm data/cache volumes on a replacement VM of the same size. No compiler or other lab job runs during either restart.

| Image | Start to green |
|---|---:|
| Official 3.9.0 | 597 s |
| 3.9.0 + PR changes | 228 s |

The stock job reported I/O stalls for 13.3% of its time. The fixed job reported CPU stalls for 12.9% and I/O stalls for 17.9%. Both reported zero OOM kills. These are single-run observations with resource-stall limits, not a controlled benchmark or an estimate of run-to-run variation. Real S3, search latency and macOS Docker Desktop were not tested. The images support AMD64/ARM64 and the example avoids `tc`, `nsenter` and host network namespaces.

This example disables authentication and uses public test credentials. Keep it isolated. Remove its volumes with `docker compose down -v` before running `./repro.sh setup` again.
