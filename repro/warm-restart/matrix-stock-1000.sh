cd "$(dirname "$(readlink -f "$0")")"; . ./matrix-lib.sh
run stock-n1000-lat0-k4 0 4
run stock-n1000-lat100-k4 100 4
run stock-n1000-lat200-k4 200 4
run stock-n1000-lat200-k32 200 32
run stock-n1000-lat200-k128 200 128
run stock-n1000-lat200-k4-snap20 200 4 --cmd "SNAP_MAX=20 docker compose -p stand up -d --force-recreate warm"
echo "=== reset warm to default snapshot pool, lat 0"
python3 harness.py latency 0; K 4
docker compose -p stand up -d --force-recreate warm
python3 -c "import harness; print(harness.wait_green(expect_active=1003))"
echo MATRIX_DONE
