# source me from the stand directory
K() { curl -s -XPUT localhost:9200/_cluster/settings -H 'Content-Type: application/json' -d "{\"persistent\":{\"cluster.routing.allocation.node_initial_primaries_recoveries\":$1}}" >/dev/null; }
# run LABEL LAT K [extra harness args...]
run() { L=$1; LAT=$2; KK=$3; shift 3; python3 harness.py latency $LAT >/dev/null; K $KK; echo "=== $L lat=$LAT k=$KK $(date -u +%T)"; python3 harness.py restart $L "$@"; }
