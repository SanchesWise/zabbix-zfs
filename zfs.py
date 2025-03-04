#!/usr/bin/env python3

import re
import json
from subprocess import check_output, DEVNULL

ZP = '/sbin/zpool'
ZFS = '/sbin/zfs'


# Runs the given command and returns a list of lines, stripped and split
# by given regex
def run(cmd, split=r'\t'):
    r = check_output(
        cmd,
        encoding='utf8',
        stderr=DEVNULL
    )

    return [re.split(split, x.strip()) for x in r.split('\n') if x.strip()]


# Read & santize file splitting by given regexp
def read_file(fn, skip=2, split=r'\s+'):
    with open(fn) as f:
        for i in range(skip):
            f.readline()

        return [re.split(split, x) for x in f.readlines()]


# Read IO stats for a given pool
def pool_io_stats(pool):
    try:
        r = read_file(f'/proc/spl/kstat/zfs/{pool}/iostats', skip=1)
    except BaseException:
        r = read_file(f'/proc/spl/kstat/zfs/{pool}/io', skip=1)

    return {x[0]: int(x[1]) for x in zip(r[0], r[1]) if x[1].isdigit()}


# Returns a list of pools with their stats
def pool_list(scrub):
    r = run([
        ZP,
        "list",
        "-Hpo",
        "name,size,allocated,free,fragmentation,capacity,dedupratio,health"
    ])

    return {x[0]: {
        'name': x[0],
        'size': int(x[1]),
        'alloc': int(x[2]),
        'free': int(x[3]),
        'frag': int(x[4]),
        'usage': int(x[5]),
        'dedup': float(x[6]),
        'scrub': int(scrub[x[0]]),
        'online': int(x[7] == 'ONLINE'),
        'io': pool_io_stats(x[0]),
    } for x in r}


def pool_status():
    r = run([
        ZP,
        "status",
        "-Pp",
    ], split=r'\s+')

    pool = ""
    scrub = {}
    for l in r:
        if l[0] == "pool:":
            pool = l[1]
            scrub[pool] = False

        if l[0] == "scan:" and ' '.join(l[1:4]) == "scrub in progress":
            scrub[pool] = True

    vdev_errors = {}
    for x in r:
        if len(x) < 5 or not x[0].startswith('/'):
            continue

        try:
            vdev_errors[x[0]] = {
                'read': int(x[2]),
                'write': int(x[3]),
                'cksum': int(x[4]),
            }
        except BaseException:
            vdev_errors[x[0]] = {
                'read': 0,
                'write': 0,
                'cksum': 0,
            }

    return scrub, vdev_errors


def vdev_list(errors):
    r = run([
        ZP,
        "list",
        "-PHvp",
    ])

    return {x[0]: {
        'name': x[0],
        'size': int(x[1]) if x[1].isdigit() else 0,
        'alloc': int(x[2]) if x[2].isdigit() else 0,
        'free': int(x[3]) if x[3].isdigit() else 0,
        'frag': int(x[6]) if x[6].isdigit() else 0,
        'usage': int(x[7]) if x[7].isdigit() else 0,
        'online': int(x[9] == 'ONLINE'),
        'errors': errors[x[0]],
    } for x in r if x[0].startswith('/')}


def zfs_list():
    r = run([
        ZFS,
        "list",
        "-Hpo",
        "name,avail,used,compressratio,referenced"
    ])

    return {x[0]: {
        'name': x[0],
        'avail': int(x[1]),
        'used': int(x[2]),
        'compress': float(x[3]),
        'referenced': int(x[4])
    } for x in r}


def slab_usage():
    return sum([int(x[2])
                for x in read_file('/proc/spl/kmem/slab') if x[2].isdigit()])


def arc_stats():
    r = {x[0]: int(x[2]) for x in read_file('/proc/spl/kstat/zfs/arcstats')}

    l1 = r['hits'] + r['misses']
    l2 = r['l2_hits'] + r['l2_misses']

    return {
        'l1': {
            'size': r['size'],
            'hitrate': r['hits'] / l1 * 100 if l1 else 0,
            'free': r['memory_available_bytes'],
            'meta_used': r['arc_meta_used'],
            'meta_limit': r['arc_meta_limit'],
        },

        'l2': {
            'usage': r['l2_size'],
            'usage_actual': r['l2_asize'],
            'hitrate': r['l2_hits'] / l2 * 100 if l2 else 0,
            'bytes_read': r['l2_read_bytes'],
            'bytes_written': r['l2_write_bytes'],
            'io_error': r['l2_io_error'],
            'cksum_bad': r['l2_cksum_bad'],
        }
    }


scrub, vdev_errors = pool_status()

r = {
    'vdevs': vdev_list(vdev_errors),
    'pools': pool_list(scrub),
    'datasets': zfs_list(),
    'arc': arc_stats(),
    'slab': slab_usage(),
}

print(json.dumps(r, indent=2))
