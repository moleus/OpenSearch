#!/usr/bin/env python3
"""Summarize jstack files of one run: where is the cluster applier thread, how many snapshot/generic threads are busy."""
import glob, re, sys, collections
d = sys.argv[1]
files = sorted(glob.glob(d + "/jstack-*.txt"))
appl = collections.Counter()
snap_busy = []
gen_busy = []
for f in files:
    txt = open(f).read()
    blocks = re.split(r"\n\n", txt)
    sb = gb = 0
    for b in blocks:
        m = re.match(r'"([^"]+)"', b)
        if not m:
            continue
        name = m.group(1)
        frames = [l.strip()[3:] for l in b.splitlines() if l.strip().startswith("at ")]
        if "clusterApplierService#updateTask" in name:
            key = "idle"
            for fr in frames:
                if "RemoteSnapshotDirectoryFactory.newDirectory" in fr: key = "newDirectory(loadShardSnapshot wait)"; break
                if "IndicesClusterStateService" in fr or "IndicesService" in fr or "IndexService" in fr: key = "other createShard work: " + fr.split("(")[0]; break
            else:
                if any("ClusterApplierService" in fr for fr in frames) and frames and "park" not in frames[0] and "LinkedTransferQueue" not in " ".join(frames[:6]):
                    key = "applier other: " + frames[0].split("(")[0]
            appl[key] += 1
        elif "[snapshot][T#" in name:
            if any("loadShardSnapshot" in fr or "readBlob" in fr or "S3" in fr or "software.amazon" in fr for fr in frames): sb += 1
        elif "[generic][T#" in name:
            if frames and not any("LinkedTransferQueue" in fr or "SynchronousQueue" in fr for fr in frames[:8]):
                gb += 1
    snap_busy.append(sb); gen_busy.append(gb)
n = len(files)
print("samples", n)
for k, v in appl.most_common(): print("  applier %-70s %3d (%.0f%%)" % (k, v, 100.0 * v / n))
if n:
    print("  snapshot threads busy in S3/loadShardSnapshot: mean %.1f max %d" % (sum(snap_busy) / n, max(snap_busy)))
    print("  generic threads not idle: mean %.1f max %d" % (sum(gen_busy) / n, max(gen_busy)))
