import asyncio

from app.pipeline.shared import runtime_budget as budget


def test_stage_limits_follow_request_deadline_and_reset_after_failure(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(budget.time, "monotonic", lambda: now[0])
    assert budget.remaining_seconds(55) == 55
    try:
        with budget.request_budget(20):
            assert budget.remaining_seconds(55) == 20
            now[0] += 18
            assert budget.remaining_seconds(55) == 2
            raise ValueError("Request failed")
    except ValueError:
        pass
    assert budget.remaining_seconds(55) == 55


def test_nested_work_cannot_extend_request_deadline(monkeypatch):
    monkeypatch.setattr(budget.time, "monotonic", lambda: 100.0)
    with budget.request_budget(10):
        with budget.request_budget(200):
            assert budget.remaining_seconds(55) == 10


def test_parallel_requests_have_independent_budgets(monkeypatch):
    monkeypatch.setattr(budget.time, "monotonic", lambda: 100.0)
    async def request(seconds):
        with budget.request_budget(seconds):
            await asyncio.sleep(0)
            return budget.remaining_seconds(55)
    async def run():
        return await asyncio.gather(request(10), request(30))
    assert asyncio.run(run()) == [10, 30]
    assert budget.remaining_seconds(55) == 55
