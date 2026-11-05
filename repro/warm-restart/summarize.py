#!/usr/bin/env python3
"""Print one table row per results/<label>/result.json."""
import glob, json, os
rows = []
for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "*", "result.json"))):
    r = json.load(open(f))
    rows.append(r)
print("%-40s %8s %8s %8s %8s %6s" % ("label", "join->green_s", "to50%", "to90%", "max_init", "shards"))
for r in rows:
    print("%-40s %8s %8s %8s %8s %6s" % (r["label"], r["node_join_to_green_s"], r.get("to_50%_s"), r.get("to_90%_s"), r["max_initializing"], r["total_active"] - 3))
