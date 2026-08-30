import asyncio

from app.workers import tasks


def test_worker_runner_reuses_one_event_loop_for_consecutive_tasks():
    loop_ids: list[int] = []

    async def record_loop() -> None:
        loop_ids.append(id(asyncio.get_running_loop()))

    tasks._close_runner()
    try:
        tasks._run(record_loop())
        tasks._run(record_loop())
    finally:
        tasks._close_runner()

    assert len(loop_ids) == 2
    assert loop_ids[0] == loop_ids[1]
