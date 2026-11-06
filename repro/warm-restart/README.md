# Warm node restart: synthetic test stand

This directory has a small stand that shows how long a `warm` node needs to start its
searchable snapshot shards after a restart.

## What the stand has

| Part | Purpose |
|---|---|
| `compose.yml` | One `cluster_manager,data` node, one `warm` node, one MinIO as S3 repository. |
| `Dockerfile.s3` | Adds the `repository-s3` plugin to a released OpenSearch image. |
| `Dockerfile.fix` | Puts a locally built `opensearch-<version>.jar` into the image from `Dockerfile.s3`. |
| `harness.py` | Creates indices, makes a snapshot, restores shards as `remote_snapshot`, injects S3 latency, restarts the warm node, and writes the measurements. |
| `analyze_jstack.py`, `analyze_collapsed.py` | Show where the cluster applier thread waits. |
| `matrix-*.sh` | The runs that produced the numbers in the issue. |

## How to run it

The stand needs Docker, `sudo` (for `tc netem`), and Python 3.

```sh
docker build -f Dockerfile.s3 -t os-s3:stock .
mkdir -p prof && chmod 777 prof
docker compose -p stand up -d                      # wait until the cluster has 2 nodes
python3 harness.py mkindices 2000                  # one shard, no replica, one document each
python3 harness.py snapshot
python3 harness.py restore 1000                    # remote_snapshot, all shards go to the warm node
python3 harness.py latency 200                     # +200 ms on every MinIO response
python3 harness.py restart my-run --dump 6         # restart warm, poll, write results/my-run/
```

`results/<label>/result.json` has `node_join_to_green_s`. This is the time from the moment the
restarted node rejoins until all shards are active. `health.csv` and `threadpool.csv` have the
time series. With `--dump N` the harness also takes a thread dump of the warm node every N seconds.

The profile runs in `matrix-*.sh` need an unpacked async-profiler release in `prof/`
(`prof/async-profiler-4.0-linux-x64/`). Skip them if you do not need a profile.

To test a patched jar, build `:server:jar`, copy the jar next to `Dockerfile.fix`, and build
`os-s3:fix`. Then start the stand with `OS_IMAGE=os-s3:fix`.

## Limits of the stand

MinIO runs on the same host as OpenSearch. The latency comes from `tc netem` on the MinIO
container and delays every response by the same time. All indices are tiny: one document,
one shard. The stand does not measure search latency.
