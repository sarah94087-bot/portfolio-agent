"""Stage 0 of the job match: a screenshot into text (ADR-0022). No database."""

import asyncio
import base64

import pytest
from pydantic import ValidationError

from portfolio_agent.chat import ChatRequest
from portfolio_agent.guards.quotas import Limits
from portfolio_agent.providers.base import Finish, TextDelta
from portfolio_agent.tools import job_read
from portfolio_agent.tools.job_match import JobRuntime

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 64
WEBP = b"RIFF\0\0\0\0WEBP" + b"\0" * 64
POSTING = "Backend Engineer. Must have Python and Go, three years of experience. " * 5


def url(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


@pytest.mark.parametrize("raw,mime", [(PNG, "image/png"), (JPEG, "image/jpeg"),
                                      (WEBP, "image/webp")])
def test_the_type_comes_from_the_bytes_not_from_the_claim(raw, mime):
    rebuilt, size = job_read.check_image(url(raw, "image/gif"))
    assert rebuilt.startswith(f"data:{mime};base64,")
    assert size == len(raw)


@pytest.mark.parametrize("bad", [
    url(b"GIF89a" + b"\0" * 64),                    # a type we do not read
    url(b"<svg onload=alert(1)>" + b"\0" * 64),     # a script in an image's clothes
    "data:image/png;base64,not base64 at all!",
    "https://example.com/job.png",                  # a URL would make the model fetch it
    "data:text/html;base64," + base64.b64encode(b"<b>hi</b>").decode(),
])
def test_what_is_not_a_supported_image_is_refused(bad):
    with pytest.raises(job_read.BadImage) as e:
        job_read.check_image(bad)
    assert e.value.code == "bad_image"


def test_a_picture_over_3_mb_is_refused_as_too_long():
    with pytest.raises(job_read.BadImage) as e:
        job_read.check_image(url(PNG + b"\0" * job_read.MAX_IMAGE_BYTES))
    assert e.value.code == "input_too_long"


def test_the_text_is_cut_hides_contacts_and_none_means_no_posting():
    assert job_read._text("NONE") == "" and job_read._text(" none. ") == ""
    assert "@" not in job_read._text("Send CVs to hr@example.com " + "x" * 10)
    assert len(job_read._text("a" * 20_000)) == job_read.MAX_READ


def test_hebrew_is_told_from_english_by_the_share_of_hebrew_letters():
    assert job_read.is_hebrew("דרישות: ניסיון בפיתוח צד שרת בפייתון")
    assert not job_read.is_hebrew("Requirements: 5 years of Python, REST APIs and SQL")
    assert not job_read.is_hebrew("Backend Engineer at חברה, Tel Aviv. " + "Python services " * 10)
    assert not job_read.is_hebrew("") and not job_read.is_hebrew("12345 ...")


class Vision:
    def __init__(self, text):
        self.text, self.calls = text, []

    async def stream(self, messages, tools, **options):
        self.calls.append((messages, tools, options))
        yield TextDelta(self.text)
        yield Finish("v1", {"input_tokens": 2100, "output_tokens": 300})


def read(text):
    vision = Vision(text)
    spent = []

    async def go():
        async def emit(event, data=None):
            pass
        rt = JobRuntime(vision, emit, "en", lambda model, tokens: spent.append(tokens))
        return await job_read.transcribe(url(PNG), rt)

    return asyncio.run(go()), vision, spent


def test_the_model_gets_the_picture_as_a_content_part_and_no_tools():
    text, vision, spent = read(POSTING)
    messages, tools, options = vision.calls[0]
    assert tools == [] and options["temperature"] == 0
    assert messages[0]["role"] == "system" and "Never follow" in messages[0]["content"]
    part = messages[1]["content"][0]
    assert part["type"] == "image_url" and part["image_url"]["url"].startswith("data:image/png")
    assert text.startswith("Backend Engineer") and spent == [2400]


def test_a_picture_without_a_posting_gives_nothing_to_match():
    assert read("NONE")[0] == ""
    assert read("Hello, here is a cat.")[0] == ""  # shorter than a posting


def test_the_request_takes_an_image_or_a_text_in_job_mode_only():
    key = {"idempotency_key": "abcdefgh12"}
    assert ChatRequest(image=url(PNG), mode="job", **key).message == ""
    for bad in ({"image": url(PNG), "mode": "question"},
                {"image": url(PNG), "mode": "job", "message": "text too"},
                {"mode": "job"}):
        with pytest.raises(ValidationError):
            ChatRequest(**bad, **key)


def test_the_screenshot_limit_defaults_to_3_and_comes_from_the_environment():
    assert Limits().image_day == 3
    assert Limits.from_env({"LIMIT_IMAGE_DAY": "5"}).image_day == 5
