from pathlib import Path
from skillpulse_crawler.history import History


def test_record_and_query_seen_key(tmp_path: Path):
    db = tmp_path / "runs.sqlite"
    with History(db) as h:
        h.record_seen("paper", "arXiv", "2406.12345")
        assert h.has_seen("paper", "arXiv", "2406.12345")
        assert not h.has_seen("paper", "arXiv", "2406.99999")


def test_create_run_and_complete(tmp_path: Path):
    db = tmp_path / "runs.sqlite"
    with History(db) as h:
        run_id = h.start_run(issue_number=37)
        h.complete_run(run_id, summary={"inserted": 5})
        run = h.get_run(run_id)
        assert run["status"] == "success"
        assert run["issue_number"] == 37