def union_length(intervals):
    total=0;end=None
    for lo,hi in sorted(intervals):
        if lo>hi:raise ValueError('区间倒置')
        if end is None or lo>end:total+=hi-lo;end=hi
        elif hi>end:total+=hi-end;end=hi
    return total
def positive_overlap(a,b):return max(a[0],b[0])<min(a[1],b[1])
def validate_relation(row,known):
    return [name for name in ['left','right'] if row[name] not in known]+([] if row['kind'] in {'parent_clip','transcode','similar'} else ['kind'])
def split_sizes(rows):
    counts={}
    for row in rows:counts[row['split']]=counts.get(row['split'],0)+1
    return counts
