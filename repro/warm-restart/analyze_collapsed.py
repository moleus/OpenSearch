#!/usr/bin/env python3
"""Wall-clock profile (collapsed stacks, async-profiler --threads) -> where does the cluster applier thread wait?
usage: analyze_collapsed.py file.collapsed [interval_ms]   (interval of the profile, default 20)"""
import sys, collections
ms = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
app = collections.Counter()
generic_wait = 0
for line in open(sys.argv[1]):
    stack, _, n = line.rpartition(" ")
    n = int(n)
    frames = stack.split(";")
    thread = frames[0]
    leaf = frames[-1]
    in_dir = any("RemoteSnapshotDirectoryFactory.newDirectory" in f for f in frames)
    if "clusterApplierService#updateTask" in thread:
        if in_dir and ("futex" in leaf or "park" in leaf):
            kind = "blocked in newDirectory (waits for loadShardSnapshot)"
        elif in_dir:
            kind = "newDirectory, local work (mkdir, fsync)"
        elif any("IndicesClusterStateService.applyClusterState" in f for f in frames):
            kind = "other work in IndicesClusterStateService.applyClusterState"
        elif any("ClusterApplierService" in f and "runTask" in f for f in frames):
            kind = "other applier work"
        else:
            kind = "idle (queue wait)"
        app[kind] += n
    if "[generic]" in thread and any("RemoteSnapshotDirectory.remoteState" in f for f in frames):
        generic_wait += n
t = sum(app.values())
print("applier thread (profile interval %.0f ms):" % ms)
for k, v in app.most_common():
    print("  %-60s %7d samples %8.1f s %5.1f%%" % (k, v, v * ms / 1000, 100.0 * v / t))
print("generic threads blocked in RemoteSnapshotDirectory.remoteState: %d samples = %.1f thread-seconds" % (generic_wait, generic_wait * ms / 1000))
