"""Small concurrency primitives for the parser.

`parse` used to download every HTTP asset and torrent strictly one after
another. These helpers let it run several downloads at once while still
capping how many hit the network simultaneously (e.g. 3 HTTP, 1 BT), which
avoids hammering hosts and keeps a single big torrent from blocking the queue.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def guarded(sem: asyncio.Semaphore, factory: Callable[[], Awaitable[T]]) -> T:
    """Await ``factory()`` while holding ``sem``.

    ``factory`` is a zero-arg callable returning a coroutine, so the coroutine
    is only created once the semaphore slot is free.
    """
    async with sem:
        return await factory()


async def run_jobs(jobs: list[Awaitable[T]]) -> list[T | BaseException]:
    """Run all jobs concurrently, returning results/exceptions in order.

    Each job is expected to acquire whatever semaphore(s) it needs internally
    (see :func:`guarded`), so this is just a thin wrapper over
    :func:`asyncio.gather` that never raises for an individual failure.
    """
    if not jobs:
        return []
    return await asyncio.gather(*jobs, return_exceptions=True)
