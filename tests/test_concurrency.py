import asyncio

from tgdl.concurrency import guarded, run_jobs


def test_guarded_caps_http_concurrency() -> None:
    async def main() -> tuple[int, list]:
        sem = asyncio.Semaphore(3)
        active = 0
        peak = 0

        async def job() -> int:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return 1

        results = await run_jobs([guarded(sem, job) for _ in range(9)])
        return peak, results

    peak, results = asyncio.run(main())
    assert peak <= 3
    assert results == [1] * 9


def test_guarded_serialises_single_slot() -> None:
    async def main() -> int:
        sem = asyncio.Semaphore(1)
        active = 0
        peak = 0

        async def job() -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

        await run_jobs([guarded(sem, job) for _ in range(5)])
        return peak

    assert asyncio.run(main()) == 1


def test_run_jobs_captures_exceptions() -> None:
    async def main() -> list:
        async def ok() -> str:
            return "ok"

        async def boom() -> None:
            raise ValueError("bad")

        return await run_jobs([ok(), boom()])

    results = asyncio.run(main())
    assert results[0] == "ok"
    assert isinstance(results[1], ValueError)


def test_run_jobs_empty() -> None:
    assert asyncio.run(run_jobs([])) == []
