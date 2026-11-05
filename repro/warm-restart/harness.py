#!/usr/bin/env python3
"""Harness for the warm-node restart repro. Stdlib only. Run on the Docker host.

  harness.py mkindices N        create N one-shard indices t-0000.. with one doc each
  harness.py snapshot           register the S3 repository and snapshot t-*
  harness.py restore N          delete t-*, restore the first N as remote_snapshot, wait green
  harness.py latency MS         set netem delay on the MinIO container (0 = remove)
  harness.py restart LABEL      restart warm, poll, write results/LABEL/*
"""
import json, os, subprocess, sys, threading, time, urllib.request, urllib.error

BASE = os.environ.get("OS_URL", "http://127.0.0.1:9200")
PROJ = os.environ.get("COMPOSE_PROJECT_NAME", "stand")
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
JCMD = "/usr/share/opensearch/jdk/bin/jcmd"


def req(method, path, body=None, timeout=120, raw=False):
    data = None
    headers = {}
    if body is not None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        headers["Content-Type"] = "application/x-ndjson" if isinstance(body, str) else "application/json"
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            txt = resp.read().decode()
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        if raw:
            return txt
        raise RuntimeError("%s %s -> %s %s" % (method, path, e.code, txt[:500]))
    return txt if raw else json.loads(txt)


def sh(cmd, check=True):
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True).stdout


def cid(svc):
    return sh("docker ps -aq --filter label=com.docker.compose.service=%s --filter label=com.docker.compose.project=%s" % (svc, PROJ)).split()[0]


def health(**kw):
    q = "&".join("%s=%s" % kv for kv in kw.items())
    return req("GET", "/_cluster/health?" + q)


def wait_green(expect_active=None, timeout=3600, label="", every=2):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        try:
            h = health()
        except Exception as e:  # noqa
            time.sleep(every)
            continue
        cur = (h["status"], h["initializing_shards"], h["unassigned_shards"], h["active_shards"])
        if cur != last and (int(time.time() - t0) % 10 == 0):
            print("  %s %.0fs %s" % (label, time.time() - t0, cur), flush=True)
            last = cur
        if h["status"] == "green" and (expect_active is None or h["active_shards"] >= expect_active):
            return time.time() - t0
        time.sleep(every)
    raise RuntimeError("timeout waiting for green")


def names(n):
    return ["t-%04d" % i for i in range(n)]


def cmd_mkindices(n):
    req("PUT", "/_cluster/settings", {"persistent": {"cluster.max_shards_per_node": 10000}})
    req("PUT", "/_index_template/t", {"index_patterns": ["t-*"], "template": {"settings": {"number_of_shards": 1, "number_of_replicas": 0}}})
    step = 100
    for s in range(0, n, step):
        lines = []
        for i in range(s, min(n, s + step)):
            lines.append(json.dumps({"index": {"_index": "t-%04d" % i}}))
            lines.append(json.dumps({"v": i, "msg": "synthetic document %d" % i}))
        r = req("POST", "/_bulk?refresh=true", "\n".join(lines) + "\n", timeout=600)
        assert not r["errors"], r["items"][:2]
        print("created", min(n, s + step), flush=True)
    req("POST", "/t-*/_flush", timeout=600)
    print("green after", wait_green(), "s")


def cmd_snapshot():
    req("PUT", "/_snapshot/s3", {"type": "s3", "settings": {"bucket": "snaps", "base_path": "repro", "max_snapshot_bytes_per_sec": "1gb"}})
    t0 = time.time()
    req("PUT", "/_snapshot/s3/snap1?wait_for_completion=false", {"indices": "t-*", "include_global_state": False})
    while True:
        s = req("GET", "/_snapshot/s3/snap1")["snapshots"][0]
        if s["state"] != "IN_PROGRESS":
            print("snapshot", s["state"], s["shards"], "%.0fs" % (time.time() - t0))
            break
        time.sleep(5)


def cmd_restore(n):
    t0 = time.time()
    req("DELETE", "/t-*", timeout=600, raw=True)
    time.sleep(2)
    body = {"indices": ",".join(names(n)), "storage_type": "remote_snapshot", "include_global_state": False,
            "index_settings": {"index.number_of_replicas": 0}}
    req("POST", "/_snapshot/s3/snap1/_restore?wait_for_completion=false", body, timeout=600)
    dt = wait_green(label="restore")
    print("restore of %d shards: %.0fs (cluster green)" % (n, dt))


def cmd_latency(ms):
    pid = sh("docker inspect -f '{{.State.Pid}}' %s" % cid("minio")).strip()
    sh("sudo nsenter -t %s -n tc qdisc del dev eth0 root" % pid, check=False)
    if int(ms) > 0:
        sh("sudo nsenter -t %s -n tc qdisc add dev eth0 root netem delay %sms" % (pid, ms))
    print(sh("sudo nsenter -t %s -n tc qdisc show dev eth0" % pid).strip())


def cmd_restart(label, dump_every=0, hot_every=0, restart_cmd=None):
    out = os.path.join(RES, label)
    os.makedirs(out, exist_ok=True)
    base = health()
    assert base["status"] == "green", base
    total = base["active_shards"]
    print("baseline active_shards", total, flush=True)
    stop = threading.Event()
    rows = []
    tp_rows = []
    marks = {}

    def poller():
        while not stop.is_set():
            ts = time.time()
            try:
                h = req("GET", "/_cluster/health?timeout=1s", timeout=5)
                rows.append((ts, h["status"], h["number_of_nodes"], h["initializing_shards"], h["unassigned_shards"], h["active_shards"]))
            except Exception as e:  # noqa
                rows.append((ts, "ERR", 0, 0, 0, 0))
            time.sleep(0.5)

    def tpoller():
        while not stop.is_set():
            ts = time.time()
            try:
                st = req("GET", "/_nodes/warm/stats/thread_pool?filter_path=nodes.*.thread_pool.snapshot,nodes.*.thread_pool.generic", timeout=5)
                n = list(st["nodes"].values())[0]["thread_pool"]
                pt = req("GET", "/_cluster/pending_tasks?filter_path=tasks.source", timeout=5)
                tp_rows.append((ts, n["snapshot"]["active"], n["snapshot"]["queue"], n["snapshot"]["largest"], n["snapshot"]["completed"],
                                n["generic"]["active"], n["generic"]["largest"], n["generic"]["completed"], len(pt.get("tasks", []))))
            except Exception:
                pass
            time.sleep(2)

    def dumper():
        i = 0
        while not stop.is_set():
            try:
                txt = sh("docker exec %s %s org.opensearch.bootstrap.OpenSearch Thread.print" % (cid("warm"), JCMD), check=False)
                if "clusterApplierService" in txt or "Full thread dump" in txt:
                    open(os.path.join(out, "jstack-%03d-%d.txt" % (i, int(time.time()))), "w").write(txt)
                    i += 1
            except Exception:
                pass
            time.sleep(dump_every)

    def hotter():
        i = 0
        while not stop.is_set():
            try:
                txt = req("GET", "/_nodes/warm/hot_threads?threads=10&interval=500ms&ignore_idle_threads=false", timeout=20, raw=True)
                open(os.path.join(out, "hot-%03d-%d.txt" % (i, int(time.time()))), "w").write(txt)
                i += 1
            except Exception:
                pass
            time.sleep(hot_every)

    ths = [threading.Thread(target=poller, daemon=True), threading.Thread(target=tpoller, daemon=True)]
    if dump_every:
        ths.append(threading.Thread(target=dumper, daemon=True))
    if hot_every:
        ths.append(threading.Thread(target=hotter, daemon=True))
    for t in ths:
        t.start()
    time.sleep(2)
    marks["restart_issued"] = time.time()
    sh(restart_cmd or "docker restart -t 60 %s" % cid("warm"))
    marks["restart_returned"] = time.time()
    # wait for the node to rejoin, then for all shards active
    deadline = time.time() + 3600
    while time.time() < deadline:
        r = [x for x in rows if x[0] > marks["restart_returned"]]
        if r and r[-1][1] == "green" and r[-1][2] == 2 and r[-1][5] >= total:
            break
        time.sleep(1)
    time.sleep(3)
    stop.set()
    time.sleep(1)
    # analysis
    after = [x for x in rows if x[0] > marks["restart_issued"]]
    left = next((x[0] for x in after if x[2] == 1 and x[1] != "ERR"), None)
    join = next((x[0] for x in after if x[0] > (left or 0) and x[2] == 2 and x[1] != "ERR"), None)
    done = next((x[0] for x in after if join and x[0] >= join and x[1] == "green" and x[2] == 2 and x[5] >= total), None)
    res = {"label": label, "total_active": total, "node_join_to_green_s": round(done - join, 1) if join and done else None,
           "restart_cmd_s": round(marks["restart_returned"] - marks["restart_issued"], 1),
           "max_initializing": max(x[3] for x in after), "rows": len(rows)}
    # 50%/90% points
    if join and done:
        for frac in (0.5, 0.9):
            tt = next((x[0] for x in after if x[0] >= join and x[5] >= frac * total), None)
            res["to_%d%%_s" % (frac * 100)] = round(tt - join, 1) if tt else None
    with open(os.path.join(out, "health.csv"), "w") as f:
        f.write("t_rel_join,status,nodes,init,unassigned,active\n")
        for x in rows:
            f.write("%.1f,%s,%d,%d,%d,%d\n" % (x[0] - (join or rows[0][0]), *x[1:]))
    with open(os.path.join(out, "threadpool.csv"), "w") as f:
        f.write("t_rel_join,snap_active,snap_queue,snap_largest,snap_completed,gen_active,gen_largest,gen_completed,pending_tasks\n")
        for x in tp_rows:
            f.write("%.1f,%s\n" % (x[0] - (join or rows[0][0]), ",".join(map(str, x[1:]))))
    json.dump(res, open(os.path.join(out, "result.json"), "w"), indent=1)
    print(json.dumps(res), flush=True)
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    c = a[0]
    if c == "mkindices": cmd_mkindices(int(a[1]))
    elif c == "snapshot": cmd_snapshot()
    elif c == "restore": cmd_restore(int(a[1]))
    elif c == "latency": cmd_latency(a[1])
    elif c == "restart":
        import argparse
        p = argparse.ArgumentParser(); p.add_argument("label"); p.add_argument("--dump", type=int, default=0); p.add_argument("--hot", type=int, default=0); p.add_argument("--cmd", default=None)
        ns = p.parse_args(a[1:])
        cmd_restart(ns.label, ns.dump, ns.hot, ns.cmd)
    else:
        sys.exit("unknown command")
