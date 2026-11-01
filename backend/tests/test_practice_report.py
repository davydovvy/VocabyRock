from datetime import date, datetime

from sqlalchemy import select

from app.models import PracticeSession, User
from app.practice_report import report

from .conftest import run


def test_parent_report_tracks_partial_and_completed_sessions(client, database):
    async def scenario():
        child = next(p for p in (await client.get("/api/profiles")).json() if p["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        pack = (await client.get("/api/packs")).json()[0]
        partial = (
            await client.post(
                "/api/practice",
                json={
                    "pack_id": pack["id"],
                    "kind": "choice",
                    "length": 2,
                    "word_ids": pack["word_ids"][:2],
                },
            )
        ).json()
        complete = (
            await client.post(
                "/api/practice",
                json={
                    "pack_id": pack["id"],
                    "kind": "type",
                    "length": 1,
                    "word_ids": pack["word_ids"][:1],
                },
            )
        ).json()
        answer = await client.post(
            f"/api/practice/{complete['id']}/answer", json={"index": 0, "answer": "wrong"}
        )
        assert answer.status_code == 200
        assert (await client.get("/api/parent/practice-report")).status_code == 403
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        today = date.today().isoformat()
        response = await client.get(
            "/api/parent/practice-report",
            params={
                "start": today,
                "end": today,
                "tz": "UTC",
                "child_id": child["id"],
            },
        )
        assert response.status_code == 200
        report = response.json()
        assert report["summary"] == {"started": 2, "completed": 1, "attempts": 1, "correct": 0}
        assert report["pagination"] == {
            "page": 1,
            "page_size": 20,
            "total_sessions": 2,
            "total_pages": 1,
        }
        assert report["packs"] == [
            {"date": today, "pack": pack["name"], "started": 2, "completed": 1}
        ]
        assert report["difficult_words"][0]["incorrect"] == 1
        finished = next(item for item in report["sessions"] if item["id"] == complete["id"])
        assert finished["finished_at"]
        assert finished["attempts"][0]["chosen"] == "wrong"
        assert finished["attempts"][0]["answered_at"].endswith("Z")
        assert (
            next(item for item in report["sessions"] if item["id"] == partial["id"])["finished_at"]
            is None
        )
        assert all(
            attempt["correct"] is None
            for attempt in next(item for item in report["sessions"] if item["id"] == partial["id"])[
                "attempts"
            ]
        )
        assert (await client.get("/api/parent/practice-report", params={"kind": "choice"})).json()[
            "summary"
        ]["started"] == 1
        assert (
            await client.get("/api/parent/practice-report", params={"tz": "bad/timezone"})
        ).status_code == 400
        assert (
            await client.get("/api/parent/practice-report", params={"page": 0})
        ).status_code == 400
        with database() as db:
            saved = db.scalar(select(PracticeSession).where(PracticeSession.id == complete["id"]))
            assert len(saved.attempt_history) == 1

    run(scenario())


def test_report_groups_session_by_parent_timezone(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        db.add(
            PracticeSession(
                user_id=child.id,
                pack_id=None,
                mode="quick",
                kind="type",
                direction="ru-en",
                tasks=[{"word_id": 1, "prompt": "кот", "accepted": ["cat"]}],
                results=[],
                attempt_history=[],
                started_at=datetime(2026, 10, 31, 23, 30),
            )
        )
        db.commit()
        report_today = report(db, date(2026, 11, 1), date(2026, 11, 1), "Europe/Moscow", None, None)
        assert report_today["summary"]["started"] == 1
        assert report_today["daily"][0]["date"] == "2026-11-01"
        report_utc = report(db, date(2026, 11, 1), date(2026, 11, 1), "UTC", None, None)
        assert report_utc["summary"]["started"] == 0


def test_history_pages_keep_full_range_totals(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        db.add_all(
            PracticeSession(
                user_id=child.id,
                pack_id=None,
                mode="quick",
                kind="type",
                direction="ru-en",
                tasks=[{"word_id": 1, "prompt": "кот", "accepted": ["cat"]}],
                results=[{"index": 0, "word_id": 1, "correct": False}],
                attempt_history=[{"index": 0, "word_id": 1, "correct": False}],
                started_at=datetime(2026, 11, 1, 12, 0),
            )
            for _ in range(21)
        )
        db.commit()
        first = report(db, date(2026, 11, 1), date(2026, 11, 1), "UTC", None, None, 1)
        second = report(db, date(2026, 11, 1), date(2026, 11, 1), "UTC", None, None, 2)
        assert first["pagination"] == {
            "page": 1,
            "page_size": 20,
            "total_sessions": 21,
            "total_pages": 2,
        }
        assert len(first["sessions"]) == 20
        assert len(second["sessions"]) == 1
        assert {item["id"] for item in first["sessions"]}.isdisjoint(
            item["id"] for item in second["sessions"]
        )
        assert (
            first["summary"]
            == second["summary"]
            == {
                "started": 21,
                "completed": 0,
                "attempts": 21,
                "correct": 0,
            }
        )
        assert first["difficult_words"][0]["incorrect"] == 21
