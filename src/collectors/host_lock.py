"""Per-host serialization for SSH-based collectors.

The VPS, Docker, and DockerLogs collectors all target the same hosts and are
launched concurrently from the aggregate node. Without coordination they log in
and run commands on a single host at the same time, which inflates that host's
CPU and corrupts the VPS collector's measurement — it ends up measuring the
other collectors' work rather than the host's real load.

Holding a per-host lock keeps one host's collectors sequential while different
hosts still run in parallel.
"""

import asyncio
import weakref
from typing import Dict


# Locks are per event loop: an asyncio.Lock binds to the loop that awaited it,
# and the scheduler creates a fresh loop for each run. Keyed on the loop object
# via a weak map so entries disappear with the loop — keying on id() would let a
# new loop inherit locks bound to a closed one, since CPython recycles ids.
_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[str, asyncio.Lock]]" = (
    weakref.WeakKeyDictionary()
)


def get_host_lock(host: str) -> asyncio.Lock:
    """
    Return the lock guarding SSH access to a host for the running event loop.

    Args:
        host: Hostname or IP of the target

    Returns:
        asyncio.Lock: Lock shared by every collector targeting this host
    """
    loop = asyncio.get_running_loop()

    loop_locks = _locks.get(loop)
    if loop_locks is None:
        loop_locks = {}
        _locks[loop] = loop_locks

    lock = loop_locks.get(host)
    if lock is None:
        lock = asyncio.Lock()
        loop_locks[host] = lock

    return lock
