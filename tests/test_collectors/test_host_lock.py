"""Tests for per-host SSH serialization."""

import asyncio
import pytest

from src.collectors.host_lock import get_host_lock


@pytest.mark.asyncio
async def test_same_host_serializes():
    """Two tasks on the same host must not overlap."""
    overlap = []
    active = 0

    async def work():
        nonlocal active
        async with get_host_lock("10.0.0.1"):
            active += 1
            overlap.append(active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(work() for _ in range(4)))

    # Never more than one holder at a time
    assert max(overlap) == 1


@pytest.mark.asyncio
async def test_different_hosts_run_in_parallel():
    """Distinct hosts must not block each other."""
    active = 0
    peak = 0

    async def work(host):
        nonlocal active, peak
        async with get_host_lock(host):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1

    await asyncio.gather(work("10.0.0.1"), work("10.0.0.2"), work("10.0.0.3"))

    assert peak == 3


@pytest.mark.asyncio
async def test_same_lock_returned_within_a_loop():
    """Repeated calls for one host share a single lock object."""
    assert get_host_lock("10.0.0.9") is get_host_lock("10.0.0.9")


def test_locks_are_not_shared_across_event_loops():
    """A fresh event loop gets fresh locks.

    The scheduler creates a new loop per run; an asyncio.Lock bound to a closed
    loop would raise when awaited.
    """
    async def grab():
        lock = get_host_lock("10.0.0.7")
        async with lock:
            pass
        return lock

    first = asyncio.run(grab())
    second = asyncio.run(grab())

    assert first is not second
