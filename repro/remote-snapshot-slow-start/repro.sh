#!/bin/sh
# Run only against the disposable Compose project in this directory.
set -eu
cd "$(dirname "$0")"

api() {
    curl --fail --silent --show-error --max-time 1800 -H 'Content-Type: application/json' "$@"
}

wait_green() {
    attempts=0
    while :; do
        health=$(curl -fsS --max-time 5 'http://localhost:9200/_cluster/health?filter_path=status,number_of_nodes' 2>/dev/null || true)
        if printf '%s' "$health" | grep -q '"green"' && printf '%s' "$health" | grep -q '"number_of_nodes":2'; then
            return 0
        fi
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 1800 ]; then
            docker compose logs --tail 30 cm warm
            return 1
        fi
        sleep 1
    done
}

case "${1:-setup}" in
    setup)
        docker compose build cm
        docker compose up -d
        attempts=0
        until curl -fsS --max-time 2 http://localhost:8474/version >/dev/null 2>&1; do
            attempts=$((attempts + 1))
            [ "$attempts" -lt 120 ] || exit 1
            sleep 1
        done
        api -X POST http://localhost:8474/proxies -d '{"name":"s3","listen":"0.0.0.0:9000","upstream":"minio:9000"}'
        wait_green
        api -X PUT http://localhost:9200/_cluster/settings -d '{"persistent":{"cluster.max_shards_per_node":10000,"cluster.routing.allocation.node_initial_primaries_recoveries":4}}'
        api -X PUT http://localhost:9200/_index_template/t -d '{"index_patterns":["t-*"],"template":{"settings":{"number_of_shards":1,"number_of_replicas":0}}}'
        i=0
        while [ "$i" -lt 1000 ]; do
            bulk_request=$(
                j=$i
                while [ "$j" -lt "$((i + 100))" ]; do
                    printf '{"index":{"_index":"t-%04d"}}\n{"v":%s}\n' "$j" "$j"
                    j=$((j + 1))
                done
            )
            bulk_response=$(printf '%s\n' "$bulk_request" | api -X POST 'http://localhost:9200/_bulk?refresh=true&timeout=5m&filter_path=errors,items.*.error' --data-binary @-)
            printf '%s\n' "$bulk_response"
            printf '%s' "$bulk_response" | grep -q '"errors":false'
            i=$((i + 100))
        done
        api -X POST 'http://localhost:9200/t-*/_flush?filter_path=_shards.failed'
        api -X PUT http://localhost:9200/_snapshot/s3 -d '{"type":"s3","settings":{"bucket":"snaps","base_path":"repro"}}'
        api -X PUT 'http://localhost:9200/_snapshot/s3/snap1?wait_for_completion=true&filter_path=snapshot.state' -d '{"indices":"t-*","include_global_state":false}'
        api -X DELETE 'http://localhost:9200/t-*'
        api -X POST http://localhost:9200/_snapshot/s3/snap1/_restore -d '{"indices":"t-*","storage_type":"remote_snapshot","include_global_state":false,"index_settings":{"index.number_of_replicas":0}}'
        wait_green
        count=$(api 'http://localhost:9200/_cat/shards/t-*?h=node,state' | grep -c '^warm *STARTED *$')
        [ "$count" -eq 1000 ] || { printf 'Expected 1000 shards on warm, got %s\n' "$count" >&2; exit 1; }
        api -X POST http://localhost:8474/proxies/s3/toxics -d '{"name":"s3-latency","type":"latency","stream":"downstream","attributes":{"latency":200,"jitter":0}}'
        printf '\nReady: 1000 searchable snapshot shards, 200 ms downstream latency. Run ./repro.sh restart\n'
        ;;
    restart)
        docker compose stop warm
        attempts=0
        while curl -fsS --max-time 5 'http://localhost:9200/_cat/nodes?h=name' | grep -q '^warm$'; do
            attempts=$((attempts + 1))
            [ "$attempts" -lt 120 ] || exit 1
            sleep 1
        done
        started=$(date +%s)
        docker compose up -d --no-deps --force-recreate warm
        attempts=0
        until curl -fsS --max-time 5 'http://localhost:9200/_cat/nodes?h=name' | grep -q '^warm$'; do
            attempts=$((attempts + 1))
            [ "$attempts" -lt 300 ] || exit 1
            sleep 1
        done
        joined=$(date +%s)
        wait_green
        finished=$(date +%s)
        printf '\nimage=%s restart_to_green_s=%s rejoin_to_green_s=%s\n' "${WARM_IMAGE:-opensearch-snapshot-repro:stock}" "$((finished - started))" "$((finished - joined))"
        ;;
    *)
        printf 'Usage: %s setup|restart\n' "$0" >&2
        exit 2
        ;;
esac
