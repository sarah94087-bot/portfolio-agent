"""The system prompt file: the canary is injected at runtime and never stored."""

import re

from portfolio_agent.agent.prompt import PLACEHOLDER, PROMPTS, VERSION, system_prompt


def test_the_file_holds_the_placeholder_once_and_no_token():
    text = (PROMPTS / f"{VERSION}.md").read_text(encoding="utf-8")
    assert text.count(PLACEHOLDER) == 1


def test_the_token_replaces_the_placeholder():
    prompt = system_prompt(token="tok-123")
    assert "tok-123" in prompt and PLACEHOLDER not in prompt


def test_without_a_token_a_random_canary_is_used():
    assert PLACEHOLDER not in system_prompt()


def test_the_prompt_names_only_tools_that_exist():
    # system.v3 told the model to use request_contact, which was never built, so it offered
    # visitors to "leave a message" (groq T1 run 11, cases d1-039 and d2-025).
    from portfolio_agent.tools.cards import RENDER_CARD
    from portfolio_agent.tools.job_match import MATCH_JOB
    from portfolio_agent.tools.portfolio import GET_PROJECT, SEARCH

    tools = {t.name for t in (SEARCH, GET_PROJECT, MATCH_JOB, RENDER_CARD)}
    text = (PROMPTS / f"{VERSION}.md").read_text(encoding="utf-8")
    fields = {"record_title"}  # names of fields in tool results, not tools
    named = set(re.findall(r"`([a-z]+_[a-z_]+)`", text)) - fields
    assert named <= tools, named - tools


def test_the_language_rule_comes_before_the_first_section():
    # English questions got Hebrew answers in groq T1 run 11 (d1-039, d1-054), with the rule
    # deep in a section full of Hebrew examples. Now it opens the prompt.
    text = (PROMPTS / f"{VERSION}.md").read_text(encoding="utf-8")
    rule = text.index("Answer in the language of the visitor's last message")
    assert rule < text.index("\n## ")


def test_every_example_has_an_english_version():
    # The model copies examples. system.v4 gave the "no information" example in Hebrew only,
    # and an English question got that sentence in Hebrew (groq T1 run 12, d1-054).
    text = (PROMPTS / f"{VERSION}.md").read_text(encoding="utf-8")
    hebrew = re.compile(r"[֐-׿]")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "Example" not in line or not hebrew.search(line):
            continue
        if any(not hebrew.search(q) for q in re.findall(r'"([^"]+)"', line)):
            continue  # the English version is on the same line
        assert line.startswith("- Example, Hebrew question"), line
        assert lines[i - 1].startswith("- Example, English question"), line
