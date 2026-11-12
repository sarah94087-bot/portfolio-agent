"""The D3-img runner's arithmetic, budget and resume, with no model."""

import asyncio
import json

from portfolio_agent.providers.base import Finish, TextDelta, ToolCall
from portfolio_agent.providers.openai_compat import ProviderError

from jobmatch.dataset import load_d3
from jobmatch.image_run import (
    CARD_JOBS,
    IMAGE_ESTIMATE,
    injected,
    items_of,
    metrics,
    passed,
    precision,
    recall,
    report,
    run_all,
    run_image,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
JOBS = load_d3()
ITEMS = items_of(JOBS)


def saved_for(items, **over):
    base = {"tokens": 3000, "text": "x" * 300, "recall": 0.97, "precision": 0.99,
            "extracted": [], "injection_followed": False}
    hebrew = {"text": "", "recall": 0.0, "precision": 0.0, "refused": True}
    return {i["key"]: {**base, **over, **(hebrew if i["lang"] == "he" else {})} for i in items}


def test_every_posting_is_a_picture_and_three_are_also_a_phone_page():
    assert len(ITEMS) == len(JOBS) + len(CARD_JOBS)
    assert {i["layout"] for i in ITEMS} == {"plain", "card"}
    assert len({i["key"] for i in ITEMS}) == len(ITEMS)
    assert {"he", "en"} == {i["lang"] for i in ITEMS}


def test_the_injected_note_is_the_last_paragraph_of_the_three_injected_postings():
    injected_jobs = [j for j in JOBS if j.injection]
    assert len(injected_jobs) == 3
    for job in injected_jobs:
        note = injected(job)
        assert note and job.description.strip().endswith(note)
    assert all(injected(j) == "" for j in JOBS if not j.injection)


def test_recall_counts_the_posting_words_read_and_precision_the_read_words_that_belong():
    assert recall("Python and Go services", "python go services extra") == 0.75
    assert precision("Python and Go services", "python go services extra") == 0.75
    assert recall("", "anything") == 1.0 and precision("anything", "") == 1.0


def test_a_run_above_the_gate_with_nothing_taken_for_a_requirement_passes():
    m = metrics(JOBS, ITEMS, saved_for(ITEMS))
    assert m["images"] == len(ITEMS) and passed(m)
    assert "D3-img: 14 of 14" in report(m)


def test_a_low_recall_a_followed_injection_or_an_empty_read_each_fail():
    assert not passed(metrics(JOBS, ITEMS, saved_for(ITEMS, recall=0.90)))
    followed = saved_for(ITEMS)
    followed["d3-09-plain"]["injection_followed"] = True
    assert not passed(metrics(JOBS, ITEMS, followed))
    empty = saved_for(ITEMS)
    english = next(i["key"] for i in ITEMS if i["lang"] == "en")
    empty[english]["text"] = ""
    m = metrics(JOBS, ITEMS, empty)
    assert m["no_posting"] == [english] and not passed(m)


def test_a_hebrew_picture_the_site_would_read_fails_and_the_recall_is_of_english_only():
    he = next(i["key"] for i in ITEMS if i["lang"] == "he")
    read = saved_for(ITEMS)
    read[he]["refused"] = False
    m = metrics(JOBS, ITEMS, read)
    assert m["hebrew_read"] == [he] and not passed(m)
    ok = metrics(JOBS, ITEMS, saved_for(ITEMS))
    assert ok["hebrew_read"] == [] and abs(ok["recall_mean"] - 0.97) < 1e-9


def test_a_hebrew_picture_is_refused_after_the_read_and_stage_1_never_runs(tmp_path):
    job = next(j for j in JOBS if j.lang == "he")
    vision = Scripted([TextDelta(job.description), Finish("v", {"input_tokens": 2100,
                                                                 "output_tokens": 300})])
    main = Scripted()
    path = tmp_path / "p.png"
    path.write_bytes(PNG)
    item = next(i for i in ITEMS if i["job"] == job.id)
    result = asyncio.run(run_image(item, job, path, vision, main))
    assert result["refused"] and result["text"] == "" and result["tokens"] == 2400
    assert main.calls == []


def test_only_pictures_that_ran_count_and_none_yet_is_not_a_pass():
    assert not passed(metrics(JOBS, ITEMS, {}))
    m = metrics(JOBS, ITEMS, saved_for(ITEMS[:2]))
    assert m["images"] == 2 and m["tokens"] == 6000


def run_with(budget, results, saved=None):
    saved = {} if saved is None else saved
    ran, slept = [], []

    async def run(item):
        ran.append(item["key"])
        outcome = results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def sleep(seconds):
        slept.append(seconds)

    asyncio.run(run_all(ITEMS, run, saved, lambda: None, budget, sleep))
    return ran, saved, slept


def test_a_run_stays_inside_its_budget_and_skips_what_is_saved():
    ok = {"tokens": 3000, "recall": 0.97}
    ran, saved, slept = run_with(2 * IMAGE_ESTIMATE, [ok, ok, ok], {ITEMS[0]["key"]: ok})
    assert ran == [ITEMS[1]["key"], ITEMS[2]["key"]] and len(saved) == 3
    assert slept and all(s > 0 for s in slept)


def test_a_limit_from_groq_ends_the_run_and_keeps_what_was_saved():
    ok = {"tokens": 3000, "recall": 0.97}
    ran, saved, _ = run_with(10**6, [ok, ProviderError("rate_day", "TPD")])
    assert len(ran) == 2 and list(saved) == [ITEMS[0]["key"]]


class Scripted:
    def __init__(self, *rounds):
        self.rounds, self.calls = list(rounds), []

    async def stream(self, messages, tools, **options):
        self.calls.append(messages)
        for event in self.rounds.pop(0):
            yield event


def test_a_picture_is_read_by_the_vision_model_then_stage_1_runs_on_what_was_read(tmp_path):
    job = next(j for j in JOBS if j.id == "d3-09")
    note = injected(job)
    posting = job.description.replace(note, "") + "\n\n" + note
    usage = {"input_tokens": 2100, "output_tokens": 300}
    vision = Scripted([TextDelta(posting), Finish("v", usage)])
    extract = json.dumps({"role_title": "Backend", "requirements": [
        {"text": "Python backend services", "kind": "must", "category": "technical",
         "query": "python"}]})
    main = Scripted([ToolCall("c", "save_requirements", extract), Finish("m", {
        "input_tokens": 900, "output_tokens": 80})])
    path = tmp_path / "d3-09-plain.png"
    path.write_bytes(PNG)
    item = next(i for i in ITEMS if i["key"] == "d3-09-plain")

    result = asyncio.run(run_image(item, job, path, vision, main))

    assert "image_url" in json.dumps(vision.calls[0]) and "image_url" not in json.dumps(main.calls)
    assert result["recall"] == 1.0 and result["injection_followed"] is False
    assert result["tokens"] == 2400 + 980 and result["extracted"] == ["Python backend services"]


def test_an_injected_note_extracted_as_a_requirement_is_caught(tmp_path):
    job = next(j for j in JOBS if j.id == "d3-09")
    note = injected(job)
    vision = Scripted([TextDelta(job.description), Finish("v", {})])
    extract = json.dumps({"role_title": "x", "requirements": [
        {"text": note, "kind": "must", "category": "other", "query": "x"}]})
    main = Scripted([ToolCall("c", "save_requirements", extract), Finish("m", {})])
    path = tmp_path / "p.png"
    path.write_bytes(PNG)
    item = next(i for i in ITEMS if i["key"] == "d3-09-plain")
    assert asyncio.run(run_image(item, job, path, vision, main))["injection_followed"] is True
