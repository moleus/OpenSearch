cd "$(dirname "$(readlink -f "$0")")"; . ./matrix-lib.sh
export WARM_IMAGE=os-s3:fix
# switch warm to the fixed image while S3 latency is 0; N=2000 is restored
python3 harness.py latency 0; K 4
docker compose -p stand up -d --force-recreate warm
python3 -c "import harness; print(harness.wait_green(expect_active=2003))"
docker exec stand-warm-1 sh -c 'ls -l /usr/share/opensearch/lib/opensearch-3.9.0.jar'
run fix-n2000-lat200-k4 200 4
python3 harness.py latency 0; K 4
python3 harness.py restore 1000
run fix-n1000-lat0-k4 0 4
run fix-n1000-lat100-k4 100 4
run fix-n1000-lat200-k4 200 4 --dump 3
run fix-n1000-lat200-k32 200 32
run fix-n1000-lat200-k128 200 128
run fix-n1000-lat0-k32 0 32
run fix-n1000-lat0-k128 0 128
run fix-n1000-lat200-k4-snap20 200 4 --cmd "SNAP_MAX=20 docker compose -p stand up -d --force-recreate warm"
run fix-n1000-lat200-k128-snap20 200 128
run fix-n1000-lat200-k4-snap1 200 4 --cmd "SNAP_MAX=1 docker compose -p stand up -d --force-recreate warm"
python3 harness.py latency 0; K 4
docker compose -p stand up -d --force-recreate warm
python3 -c "import harness; print(harness.wait_green(expect_active=1003))"
python3 harness.py restore 500
run fix-n500-lat200-k4 200 4
AP=/prof/async-profiler-4.0-linux-x64/lib/libasyncProfiler.so
PROF="-Xms2g -Xmx2g -XX:+UnlockDiagnosticVMOptions -XX:+DebugNonSafepoints -agentpath:$AP=start,event=wall,interval=20ms,threads,jfr,timeout=300,file=/prof/fix-n500-wall.jfr"
run fix-n500-lat200-k4-prof 200 4 --dump 10 --cmd "WARM_JAVA_OPTS='$PROF' docker compose -p stand up -d --force-recreate warm"
python3 harness.py latency 0
echo MATRIX_FIX_DONE
