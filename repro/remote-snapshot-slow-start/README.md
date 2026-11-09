# Slow searchable snapshot startup

Two OpenSearch 3.9.0 nodes and MinIO, with Toxiproxy adding 200 ms to S3 responses. The same 1000 one-shard indices run first with the release server jar and then with the PR's changes. No host network namespaces or Linux traffic-control commands are needed.

Requires Docker Compose v2, curl and a POSIX shell. Give Docker at least 8 GiB RAM to run the cluster, 12 GiB RAM for fixed-image compilation, and 15 GiB free disk. On Linux and Docker Desktop, the Docker VM must have `vm.max_map_count` at least 262144. If needed, run `docker run --rm --privileged alpine:3.20 sysctl -w vm.max_map_count=262144` to set it in that VM.

Fetch the small example and start a fresh, disposable Compose project:

```sh
git clone --depth 1 --filter=blob:none --sparse --branch repro-remote-snapshot-slow-start https://github.com/moleus/OpenSearch.git snapshot-repro
git -C snapshot-repro sparse-checkout set repro/remote-snapshot-slow-start
cd snapshot-repro/repro/remote-snapshot-slow-start
./repro.sh setup
./repro.sh restart
```

Build the fixed image, then change only the warm node's image tag and repeat the restart:

```sh
docker build --target fixed -t opensearch-snapshot-repro:fixed .
WARM_IMAGE=opensearch-snapshot-repro:fixed ./repro.sh restart
```

The first command can take several minutes. The Dockerfile builds OpenSearch 3.9.0 with `fix.patch`, the complete production-code diff of [PR #23563](https://github.com/opensearch-project/OpenSearch/pull/23563) at commit `5d346deda1ec71d8293ea5faa0ed722c8a83e39f` against `bd43697b7131561096890f88cce5d909bfd30764`. Only the resulting server jar replaces the release jar; the S3 plugin and all other distribution files are identical. The patch is included so the build does not depend on an unmerged branch remaining available.

No prebuilt image is published. Use the one-line local build above; the lab comparison uses the same build.

Each restart prints both restart-to-green and rejoin-to-green seconds. The restart timer begins just before starting the replacement container, after the old node has left. Rejoin is detected by polling the cluster-manager node's `/_cat/nodes`; green is polled once per second. The reported intervals therefore have approximately one-second resolution. Setup checks that all 1000 restored shards are started on the warm node before it adds latency. Repeated runs preserve the warm cache; the remote snapshot metadata must still be loaded after every restart.

Do not use this unauthenticated setup or these public test credentials outside an isolated local test environment. To reset only this example's data, run `docker compose down -v` and then `./repro.sh setup` again.

## Lab results

Linux AMD64, 2 vCPU with full CPU share, 12 GiB RAM; 1000 searchable snapshot shards, four concurrent recoveries, snapshot pool max 5, 200 ms downstream Toxiproxy latency. One restart per variant, with the same snapshot and cache preserved.

| Warm image | Rejoin to green | Start to green |
|---|---:|---:|
| Stock 3.9.0 | 480 s | 520 s |
| 3.9.0 + PR changes | 194 s | 232 s |

The stock job finished without a lab stall warning. The fixed job reported CPU stalls for 16.4% and I/O stalls for 26.8% of the job, with zero OOM kills. These are indicative single-run observations, not a controlled benchmark or an estimate of run-to-run variation. Real S3 and search latency were not tested. macOS Docker Desktop was not run in the lab; the example uses POSIX shell and AMD64/ARM64 images without Linux host network commands.
