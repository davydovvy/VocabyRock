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
from app.models import AppSettings, Pack, PracticeSession, Progress, User, Word, now
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
        for kind in ("match", "flashcard", "choice", "type", "listen"):
            for direction in ("en-ru", "ru-en"):
                practice = create_practice(db, child, None, "all", kind, direction, 10)
                public = public_session(practice)
                assert public["tasks"]
                if kind == "match":
                    assert len(public["tasks"]) == 8
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
                if kind == "match":
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


def test_big_match_scores_first_check_and_requires_corrections(client):
    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        child = next(profile for profile in profiles if profile["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        pack = (await client.get("/api/packs")).json()[0]
        session = (
            await client.post(
                "/api/practice",
                json={"pack_id": pack["id"], "kind": "match", "direction": "ru-en"},
            )
        ).json()
        assert session["direction"] == "en-ru"
        assert len(session["tasks"]) == len(session["match_options"]) == 8
        assert all("answer" not in task and "token" not in task for task in session["tasks"])
        assert (await client.get("/api/progress")).json() == []

        url = f"/api/practice/{session['id']}/match-all"
        options = session["match_options"]
        incomplete = [
            {"index": index, "option_id": option["token"]}
            for index, option in enumerate(options[:-1])
        ]
        assert (await client.post(url, json={"pairs": incomplete})).status_code == 400
        duplicate = incomplete + [{"index": 7, "option_id": options[0]["token"]}]
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
        assert not checked["finished"] and len(checked["results"]) == 8
        assert sum(result["correct"] for result in checked["results"]) == 6
        assert sum(task["locked"] for task in checked["tasks"]) == 6
        assert all(result["answer"] == "" for result in checked["results"])
        assert checked["results"][0]["chosen"] != checked["results"][0]["answer"]
        progress = (await client.get("/api/progress")).json()
        assert len(progress) == 8
        assert sum(row["incorrect"] for row in progress) == 2
        assert (await client.post(url, json={"pairs": pairs})).status_code == 400
        stats_before = (await client.get("/api/stats")).json()
        locked_change = [dict(pair) for pair in pairs]
        locked_change[2]["option_id"], locked_change[3]["option_id"] = (
            locked_change[3]["option_id"],
            locked_change[2]["option_id"],
        )
        assert (await client.post(url, json={"pairs": locked_change})).status_code == 400
        pairs[0]["option_id"], pairs[1]["option_id"] = pairs[1]["option_id"], pairs[0]["option_id"]
        finished = (await client.post(url, json={"pairs": pairs})).json()
        assert finished["finished"]
        assert all(task["locked"] for task in finished["tasks"])
        assert all(result["answer"] for result in finished["results"])
        assert (await client.get("/api/progress")).json() == progress
        stats_after = (await client.get("/api/stats")).json()
        assert stats_after["user"]["xp"] == stats_before["user"]["xp"]
        assert stats_after["user"]["stars"] == stats_before["user"]["stars"]

    run(scenario())


def test_big_match_requires_eight_distinct_pairs_and_respects_match_setting(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        pack = db.scalar(select(Pack).where(Pack.name == "Animals"))
        for word in pack.words[:3]:
            db.delete(word)
        db.flush()
        with pytest.raises(HTTPException, match="needs 8 different words"):
            create_practice(db, child, pack.id, "all", "match", "en-ru", 10)
        settings = db.get(AppSettings, 1)
        settings.allowed_exercises = [
            kind for kind in settings.allowed_exercises if kind != "match"
        ]
        db.flush()
        with pytest.raises(HTTPException, match="turned off"):
            create_practice(db, child, None, "all", "match", "en-ru", 10)


def test_big_match_chooses_display_translations_with_one_solution(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        words = [
            Word(english="alpha", translations=["общий", "уникальный"]),
            Word(english="beta", translations=["общий", "особый"]),
        ] + [Word(english=f"word {index}", translations=[f"перевод {index}"]) for index in range(6)]
        db.add_all(words)
        db.flush()
        sessions = [
            public_session(
                create_practice(
                    db, child, None, "all", "match", "ru-en", 2, [word.id for word in words]
                )
            )
            for _ in range(4)
        ]
        for session in sessions:
            assert session["direction"] == "en-ru"
            assert len(session["tasks"]) == len(session["match_options"]) == 8
            labels = {option["text"] for option in session["match_options"]}
            assert "общий" not in labels
            assert {"уникальный", "особый"} <= labels
        assert len({tuple(task["prompt"] for task in session["tasks"]) for session in sessions}) > 1
        assert (
            len(
                {
                    tuple(option["text"] for option in session["match_options"])
                    for session in sessions
                }
            )
            > 1
        )


def test_retired_match_sessions_remain_readable(database):
    with database() as db:
        child = db.scalar(select(User).where(User.role == "child"))
        word = db.scalar(select(Word))
        for kind in ("match", "match_all"):
            practice = PracticeSession(
                user_id=child.id,
                kind=kind,
                mode="all",
                direction="en-ru",
                tasks=[
                    {
                        "word_id": word.id,
                        "prompt": word.english,
                        "answer": word.translations[0],
                        "token": 123,
                    }
                ],
                results=[
                    {
                        "index": 0,
                        "correct": True,
                        "answer": word.translations[0],
                        "word_id": word.id,
                    }
                ],
                finished_at=now(),
            )
            db.add(practice)
            db.flush()
            public = public_session(practice)
            assert public["kind"] == kind
            assert public["finished"]
            assert public["match_options"] == [{"token": 123, "text": word.translations[0]}]
        with pytest.raises(HTTPException, match="moved to Big Match"):
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


def test_word_learning_needs_two_unassisted_exact_english_answers(client, database):
    async def scenario():
        child = next(p for p in (await client.get("/api/profiles")).json() if p["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        pack = (await client.get("/api/packs")).json()[0]
        word = next(
            w for w in (await client.get("/api/words")).json() if w["id"] == pack["word_ids"][0]
        )

        async def answer(kind, direction, value, hint=False):
            session = (
                await client.post(
                    "/api/practice",
                    json={
                        "kind": kind,
                        "direction": direction,
                        "mode": "all",
                        "length": 1,
                        "word_ids": [word["id"]],
                    },
                )
            ).json()
            if hint:
                await client.post(f"/api/practice/{session['id']}/hint/0", json={"level": 1})
            body = {"index": 0, "answer": value}
            if kind == "choice":
                with database() as db:
                    saved = db.get(PracticeSession, session["id"])
                    body = {
                        "index": 0,
                        "option_id": next(
                            o["token"]
                            for o in saved.tasks[0]["options"]
                            if o["word_id"] == word["id"]
                        ),
                    }
            return (await client.post(f"/api/practice/{session['id']}/answer", json=body)).json()

        async def progress():
            return next(
                (
                    row
                    for row in (await client.get("/api/progress")).json()
                    if row["word_id"] == word["id"] and row["direction"] == "ru-en"
                ),
                None,
            )

        await answer("choice", "en-ru", "")
        await answer("type", "en-ru", word["translations"][0])
        assert (await client.get("/api/stats")).json()["learned"] == 0
        await answer("type", "ru-en", word["english"])
        assert (await progress())["typed_streak"] == 1
        await answer("type", "ru-en", word["english"], hint=True)
        assert (await progress())["typed_streak"] == 0
        await answer("type", "ru-en", word["english"])
        assert (await progress())["typed_streak"] == 1
        with database() as db:
            db.get(AppSettings, 1).lenient_typos = True
            db.commit()
        assert (await answer("type", "ru-en", word["english"][:-1]))["correct"]
        assert (await progress())["typed_streak"] == 0
        await answer("type", "ru-en", word["english"])
        assert (await progress())["typed_streak"] == 1
        await answer("type", "ru-en", word["english"].upper())
        assert (await progress())["learned"] is True
        assert (await client.get("/api/stats")).json()["learned"] == 1
        assert (await client.get("/api/packs")).json()[0]["learned_count"] == 1

    run(scenario())


def test_pack_test_only_contains_unlearned_words_and_ninety_percent_marks_pack(client, database):
    async def scenario():
        child = next(p for p in (await client.get("/api/profiles")).json() if p["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        pack = (await client.get("/api/packs")).json()[0]
        assert pack["word_count"] == 10
        assert not pack["learned"]
        assert (await client.post("/api/practice", json={"mode": "test"})).status_code == 400
        session = (
            await client.post(
                "/api/practice",
                json={
                    "mode": "test",
                    "pack_id": pack["id"],
                    "kind": "choice",
                    "direction": "en-ru",
                    "length": 1,
                },
            )
        ).json()
        assert session["mode"] == "test" and session["kind"] == "type"
        assert session["direction"] == "ru-en"
        assert len(session["tasks"]) == 10
        assert (
            await client.post(f"/api/practice/{session['id']}/hint/0", json={"level": 1})
        ).status_code == 400
        with database() as db:
            db.get(AppSettings, 1).lenient_typos = True
            first_word = db.get(Word, pack["word_ids"][0])
            db.commit()
        first_index = next(
            index
            for index, task in enumerate(session["tasks"])
            if task["prompt"] == first_word.translations[0]
        )
        misspelled = (
            await client.post(
                f"/api/practice/{session['id']}/answer",
                json={"index": first_index, "answer": first_word.english[:-1]},
            )
        ).json()
        assert not misspelled["correct"]

        with database() as db:
            words = {w.id: w.english for w in db.scalars(select(Word)).all()}
            for word_id in pack["word_ids"][:8]:
                progress = update_progress(db, child["id"], word_id, "ru-en", True)
                progress.typed_streak = 2
                progress.learned = True
            db.commit()
        pack = (await client.get("/api/packs")).json()[0]
        assert pack["learned_count"] == 8 and not pack["learned"]
        with database() as db:
            ninth = update_progress(db, child["id"], pack["word_ids"][8], "ru-en", True)
            ninth.typed_streak = 2
            ninth.learned = True
            db.commit()
        pack = (await client.get("/api/packs")).json()[0]
        assert pack["learned_count"] == 9 and pack["learned"]
        remaining = pack["word_ids"][-1]
        session = (
            await client.post("/api/practice", json={"mode": "test", "pack_id": pack["id"]})
        ).json()
        assert len(session["tasks"]) == 1
        assert session["tasks"][0]["prompt"] == next(
            w["translations"][0]
            for w in (await client.get("/api/words")).json()
            if w["id"] == remaining
        )
        assert (
            await client.post(
                f"/api/practice/{session['id']}/answer",
                json={"index": 0, "answer": words[remaining]},
            )
        ).json()["correct"]
        assert (await client.get("/api/packs")).json()[0]["learned_count"] == 9
        session = (
            await client.post("/api/practice", json={"mode": "test", "pack_id": pack["id"]})
        ).json()
        assert len(session["tasks"]) == 1
        assert (
            await client.post(
                f"/api/practice/{session['id']}/answer",
                json={"index": 0, "answer": words[remaining]},
            )
        ).json()["correct"]
        assert (await client.get("/api/packs")).json()[0]["learned_count"] == 10
        assert (
            await client.post("/api/practice", json={"mode": "test", "pack_id": pack["id"]})
        ).status_code == 400

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


def test_parent_can_set_each_child_word_learned_without_erasing_practice(client, database):
    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        children = [profile for profile in profiles if profile["role"] == "child"]
        await client.post("/api/auth/child", json={"user_id": children[0]["id"]})
        pack = (await client.get("/api/packs")).json()[0]
        word_id = pack["word_ids"][0]
        body = {"child_id": children[0]["id"], "word_id": word_id, "learned": True}
        assert (await client.put("/api/progress/learned", json=body)).status_code == 403
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        assert (await client.put("/api/progress/learned", json=body)).json() == {"learned": True}
        rows = (await client.get(f"/api/progress?child_id={children[0]['id']}")).json()
        assert len(rows) == 1
        assert rows[0]["direction"] == "ru-en" and rows[0]["learned"]
        assert rows[0]["attempts"] == 0
        assert (await client.get(f"/api/stats?child_id={children[0]['id']}")).json()["learned"] == 1
        assert (await client.get(f"/api/stats?child_id={children[1]['id']}")).json()["learned"] == 0
        await client.post("/api/auth/child", json={"user_id": children[0]["id"]})
        assert (await client.get("/api/packs")).json()[0]["learned_count"] == 1
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})

        with database() as db:
            progress = db.get(Progress, rows[0]["id"])
            progress.attempts = 3
            progress.correct = 2
            progress.typed_streak = 2
            db.commit()

        body["learned"] = False
        assert (await client.put("/api/progress/learned", json=body)).json() == {"learned": False}
        rows = (await client.get(f"/api/progress?child_id={children[0]['id']}")).json()
        assert len(rows) == 1
        assert rows[0]["attempts"] == 3 and rows[0]["correct"] == 2
        assert rows[0]["typed_streak"] == 0 and not rows[0]["learned"]
        assert (await client.put("/api/progress/learned", json=body)).json() == {"learned": False}
        body["child_id"] = children[1]["id"]
        body["learned"] = True
        assert (await client.put("/api/progress/learned", json=body)).json() == {"learned": True}
        assert (await client.get(f"/api/stats?child_id={children[1]['id']}")).json()["learned"] == 1
        assert (
            await client.put("/api/progress/learned", json={**body, "child_id": profiles[0]["id"]})
        ).status_code == 400
        assert (
            await client.put("/api/progress/learned", json={**body, "word_id": 99999})
        ).status_code == 404

    run(scenario())
