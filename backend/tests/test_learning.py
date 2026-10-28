from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.learning import (
    check_text,
    create_practice,
    normalize,
    public_session,
    submit_answer,
    update_progress,
)
from app.models import AppSettings, Pack, Progress, User, Word, now
from app.seed import seed

from .conftest import run


def test_answer_checking_and_multiple_translations(database):
    with database() as db:
        settings = db.get(AppSettings, 1)
        assert check_text("  КОШКА  ", ["кошка", "кот"], settings)
        assert check_text("кот", ["кошка", "кот"], settings)
        assert check_text("елка", ["ёлка"], settings)
        settings.fold_yo = False
        assert not check_text("елка", ["ёлка"], settings)
        assert not check_text("кошкa", ["кошка"], settings)
        assert normalize("  Red   Apple! ") == "red apple"
        settings.lenient_typos = True
        assert check_text("aple", ["apple"], settings)


def test_spaced_repetition_and_separate_children(database):
    with database() as db:
        children = db.scalars(select(User).where(User.role == "child").order_by(User.id)).all()
        word = db.scalar(select(Word))
        for _ in range(4):
            progress = update_progress(db, children[0].id, word.id, "en-ru", True)
            db.flush()
        assert progress.status in ("review", "mastered")
        assert progress.interval_days >= 4
        assert progress.next_review_at > now() + timedelta(days=1)
        update_progress(db, children[0].id, word.id, "ru-en", False)
        db.flush()
        assert db.scalar(select(Progress).where(Progress.user_id == children[1].id)) is None
        assert (
            db.scalar(
                select(Progress).where(
                    Progress.user_id == children[0].id, Progress.direction == "ru-en"
                )
            ).status
            == "learning"
        )
        update_progress(db, children[0].id, word.id, "en-ru", False)
        assert progress.interval_days == 0


def test_all_exercise_generation_and_unambiguous_options(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        db.add(Word(english="bank", translations=["банк"]))
        db.add(Word(english="bank", translations=["берег"]))
        db.add(Word(english="shore", translations=["берег"]))
        db.flush()
        for kind in ("match", "match_all", "flashcard", "choice", "type", "listen"):
            for direction in ("en-ru", "ru-en"):
                practice = create_practice(db, child, None, "all", kind, direction, 10)
                public = public_session(practice)
                assert public["tasks"]
                if kind in ("match", "match_all"):
                    assert len(public["tasks"]) == (10 if kind == "match_all" else 5)
                    assert len({t["prompt"].casefold() for t in public["tasks"]}) == len(
                        public["tasks"]
                    )
                    assert len({o["text"].casefold() for o in public["match_options"]}) == len(
                        public["match_options"]
                    )
                if kind == "choice" or kind == "listen" and direction == "en-ru":
                    for task in public["tasks"]:
                        labels = [x["text"].casefold() for x in task["options"]]
                        assert len(labels) == len(set(labels))
                        assert len(labels) == 4
                assert all("accepted" not in t and "word_id" not in t for t in public["tasks"])
                if kind == "match_all":
                    assert all(
                        "answer" not in task and "token" not in task for task in public["tasks"]
                    )


def test_practice_saves_progress_and_rewards(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        practice = create_practice(db, child, None, "all", "choice", "en-ru", 3)
        for index, task in enumerate(practice.tasks):
            right = next(x for x in task["options"] if x["word_id"] == task["word_id"])
            result = submit_answer(db, practice, index, None, right["token"], None)
            assert result["correct"]
        assert result["finished"]
        db.refresh(child)
        assert child.xp == 15
        assert child.stars == 1
        assert len(db.scalars(select(Progress).where(Progress.user_id == child.id)).all()) == 3


def test_match_all_checks_ten_pairs_only_after_complete_submission(client):
    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        child = next(profile for profile in profiles if profile["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        pack = (await client.get("/api/packs")).json()[0]
        session = (
            await client.post(
                "/api/practice",
                json={"pack_id": pack["id"], "kind": "match_all", "direction": "ru-en"},
            )
        ).json()
        assert session["direction"] == "en-ru"
        assert len(session["tasks"]) == len(session["match_options"]) == 10
        assert all("answer" not in task and "token" not in task for task in session["tasks"])
        assert (await client.get("/api/progress")).json() == []

        url = f"/api/practice/{session['id']}/match-all"
        options = session["match_options"]
        incomplete = [
            {"index": index, "option_id": option["token"]}
            for index, option in enumerate(options[:-1])
        ]
        assert (await client.post(url, json={"pairs": incomplete})).status_code == 400
        duplicate = incomplete + [{"index": 9, "option_id": options[0]["token"]}]
        assert (await client.post(url, json={"pairs": duplicate})).status_code == 400
        assert (
            await client.post(
                f"/api/practice/{session['id']}/answer",
                json={"index": 0, "option_id": options[0]["token"]},
            )
        ).status_code == 400
        assert (await client.get("/api/progress")).json() == []

        words = {
            word["english"]: word["translations"][0]
            for word in (await client.get("/api/words")).json()
        }
        token_for_translation = {option["text"]: option["token"] for option in options}
        pairs = [
            {"index": index, "option_id": token_for_translation[words[task["prompt"]]]}
            for index, task in enumerate(session["tasks"])
        ]
        pairs[0]["option_id"], pairs[1]["option_id"] = pairs[1]["option_id"], pairs[0]["option_id"]
        checked = (await client.post(url, json={"pairs": pairs})).json()
        assert checked["finished"] and len(checked["results"]) == 10
        assert sum(result["correct"] for result in checked["results"]) == 8
        assert checked["results"][0]["chosen"] != checked["results"][0]["answer"]
        progress = (await client.get("/api/progress")).json()
        assert len(progress) == 10
        assert sum(row["incorrect"] for row in progress) == 2
        assert (await client.post(url, json={"pairs": pairs})).status_code == 400

    run(scenario())


def test_match_all_requires_ten_distinct_pairs_and_respects_match_setting(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        pack = db.scalar(select(Pack).where(Pack.name == "Animals"))
        db.delete(pack.words[0])
        db.flush()
        with pytest.raises(HTTPException, match="needs 10 different words"):
            create_practice(db, child, pack.id, "all", "match_all", "en-ru", 10)
        settings = db.get(AppSettings, 1)
        settings.allowed_exercises = [
            kind for kind in settings.allowed_exercises if kind != "match"
        ]
        db.flush()
        with pytest.raises(HTTPException, match="turned off"):
            create_practice(db, child, None, "all", "match_all", "en-ru", 10)


def test_api_child_flow_and_progress(client):
    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        child = next(p for p in profiles if p["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        pack = (await client.get("/api/packs")).json()[0]
        session = (
            await client.post(
                "/api/practice",
                json={"pack_id": pack["id"], "kind": "type", "direction": "en-ru", "length": 1},
            )
        ).json()
        answer = (
            await client.post(
                f"/api/practice/{session['id']}/answer", json={"index": 0, "answer": "wrong"}
            )
        ).json()
        assert answer["finished"] and not answer["correct"]
        assert (await client.get("/api/stats")).json()["studying"] == 1
        assert (await client.get("/api/progress")).json()[0]["incorrect"] == 1

    run(scenario())


def test_type_hints_hide_answer_and_record_revealed_word_as_mistake(client, database):
    with database() as db:
        word = Word(english="Monday", translations=["понедельник"], ipa="/ˈmʌndeɪ/")
        db.add(word)
        db.commit()
        word_id = word.id

    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        child = next(profile for profile in profiles if profile["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        session = (
            await client.post(
                "/api/practice",
                json={"kind": "type", "direction": "ru-en", "length": 1, "word_ids": [word_id]},
            )
        ).json()
        session_id = session["id"]
        assert session["tasks"][0]["prompt"] == "понедельник"
        assert "accepted" not in session["tasks"][0]

        url = f"/api/practice/{session_id}/hint/0"
        assert (await client.post(url, json={"level": 1})).json() == {"hint": "M----y"}
        assert (await client.get("/api/progress")).json() == []
        assert (await client.post(url, json={"level": 2})).json() == {"hint": "Monday"}
        assert (await client.post(url, json={"level": 2})).json() == {"hint": "Monday"}
        progress = (await client.get("/api/progress")).json()
        assert progress[0]["incorrect"] == 1
        assert progress[0]["attempts"] == 1
        assert (
            "full_hint_used"
            not in (await client.get(f"/api/practice/{session_id}")).json()["tasks"][0]
        )

        result = (
            await client.post(
                f"/api/practice/{session_id}/answer", json={"index": 0, "answer": "Monday"}
            )
        ).json()
        assert result["assisted"] and not result["correct"]
        assert (await client.get("/api/progress")).json()[0]["attempts"] == 1
        assert (await client.post(url, json={"level": 1})).status_code == 400
        mistakes = (
            await client.post(
                "/api/practice",
                json={
                    "kind": "type",
                    "direction": "ru-en",
                    "mode": "mistakes",
                    "word_ids": [word_id],
                },
            )
        ).json()
        assert len(mistakes["tasks"]) == 1

    run(scenario())


def test_demo_seed_does_not_return_after_pack_deletion(database):
    with database() as db:
        for pack in db.scalars(select(Pack)).all():
            db.delete(pack)
        db.commit()
        seed(db)
        assert db.scalars(select(Pack)).all() == []


def test_homonyms_need_context_and_audio_skips_them(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        money = Word(english="bank", translations=["банк"])
        river = Word(english="bank", translations=["берег"])
        db.add_all([money, river])
        db.flush()
        with pytest.raises(HTTPException):
            create_practice(db, child, None, "all", "choice", "en-ru", 1, [money.id])
        money.example_en = "I keep money at the bank."
        practice = create_practice(db, child, None, "all", "choice", "en-ru", 1, [money.id])
        assert practice.tasks[0]["hint"] == money.example_en
        with pytest.raises(HTTPException):
            create_practice(db, child, None, "all", "listen", "en-ru", 1, [money.id])


def test_progress_reset_requires_parent_confirmation(client):
    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        child = next(p for p in profiles if p["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        session = (await client.post("/api/practice", json={"kind": "type", "length": 1})).json()
        await client.post(
            f"/api/practice/{session['id']}/answer", json={"index": 0, "answer": "wrong"}
        )
        rows = (await client.get("/api/progress")).json()
        assert len(rows) == 1
        assert (
            await client.post(
                "/api/progress/reset", json={"child_id": child["id"], "confirm": True}
            )
        ).status_code == 403
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        body = {"child_id": child["id"], "word_id": rows[0]["word_id"], "confirm": False}
        assert (await client.post("/api/progress/reset", json=body)).status_code == 400
        body["confirm"] = True
        assert (await client.post("/api/progress/reset", json=body)).json()["deleted"] == 1
        assert (await client.get(f"/api/progress?child_id={child['id']}")).json() == []

    run(scenario())
