cd "$(dirname "$(readlink -f "$0")")"; . ./matrix-lib.sh
# N=1000 is restored; lat 0 with high throttle
run stock-n1000-lat0-k32 0 32
run stock-n1000-lat0-k128 0 128
# N=500: plain run, then wall-clock profile run
python3 harness.py latency 0; K 4
python3 harness.py restore 500
run stock-n500-lat200-k4 200 4
AP=/prof/async-profiler-4.0-linux-x64/lib/libasyncProfiler.so
PROF="-Xms2g -Xmx2g -XX:+UnlockDiagnosticVMOptions -XX:+DebugNonSafepoints -agentpath:$AP=start,event=wall,interval=20ms,threads,jfr,timeout=300,file=/prof/stock-n500-wall.jfr"
run stock-n500-lat200-k4-prof 200 4 --dump 10 --cmd "WARM_JAVA_OPTS='$PROF' docker compose -p stand up -d --force-recreate warm"
python3 harness.py latency 0
docker compose -p stand up -d --force-recreate warm
python3 -c "import harness; print(harness.wait_green(expect_active=503))"
# N=2000
python3 harness.py restore 2000
run stock-n2000-lat200-k4 200 4
python3 harness.py latency 0
echo MATRIX_N_DONE
