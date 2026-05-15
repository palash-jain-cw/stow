from unittest.mock import AsyncMock, MagicMock
import pytest


EXPECTED_JOB_IDS = {
    "generate_recurring",
    "auto_post",
    "fetch_prices_evening",
    "fetch_prices_morning",
}


def _mock_schedule(job_id, next_fire_time=None):
    s = MagicMock()
    s.id = job_id
    s.next_fire_time = next_fire_time
    s.paused = False
    return s


@pytest.fixture()
def scheduler_client(client):
    mock = MagicMock()
    mock.get_schedules = AsyncMock(return_value=[
        _mock_schedule(jid) for jid in EXPECTED_JOB_IDS
    ])
    mock.add_schedule = AsyncMock(return_value="new-schedule-id")
    client.app.state.scheduler = mock
    yield client, mock


# ── Slice 1: GET /scheduler/jobs ─────────────────────────────────────────────

def test_list_jobs_returns_all_four(scheduler_client):
    client, _ = scheduler_client
    resp = client.get("/scheduler/jobs")
    assert resp.status_code == 200
    ids = {j["id"] for j in resp.json()}
    assert ids == EXPECTED_JOB_IDS


# ── Slice 2: POST /scheduler/jobs/{job_id}/trigger (valid) ───────────────────

def test_trigger_known_job_returns_204(scheduler_client):
    client, mock = scheduler_client
    resp = client.post("/scheduler/jobs/fetch_prices_evening/trigger")
    assert resp.status_code == 204
    mock.add_schedule.assert_called_once()


# ── Slice 3: POST /scheduler/jobs/{job_id}/trigger (unknown) ─────────────────

def test_trigger_unknown_job_returns_404(scheduler_client):
    client, _ = scheduler_client
    resp = client.post("/scheduler/jobs/nonexistent_job/trigger")
    assert resp.status_code == 404


# ── Slice 4: job error handling ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_job_exception_is_swallowed(caplog, monkeypatch):
    from unittest.mock import MagicMock
    from stow.scheduler import _job_generate_recurring

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=MagicMock())
    mock_cm.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("stow.scheduler.Session", lambda *a, **kw: mock_cm)
    monkeypatch.setattr("stow.scheduler.create_queue_entries_for_today",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))

    import logging
    with caplog.at_level(logging.ERROR, logger="stow.scheduler"):
        await _job_generate_recurring()
    assert "boom" in caplog.text


# ── Slice 5: IST timezone on cron schedules ───────────────────────────────────

def test_schedules_use_ist_timezone():
    from stow.scheduler import SCHEDULES, IST
    from apscheduler.triggers.cron import CronTrigger
    for job_id, _, trigger in SCHEDULES:
        assert isinstance(trigger, CronTrigger), f"{job_id} trigger is not CronTrigger"
        assert trigger.timezone == IST, f"{job_id} not using IST"
