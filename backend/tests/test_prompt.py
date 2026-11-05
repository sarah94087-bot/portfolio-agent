"""The system prompt file: the canary is injected at runtime and never stored."""

from portfolio_agent.agent.prompt import PLACEHOLDER, PROMPTS, VERSION, system_prompt


def test_the_file_holds_the_placeholder_once_and_no_token():
    text = (PROMPTS / f"{VERSION}.md").read_text(encoding="utf-8")
    assert text.count(PLACEHOLDER) == 1


def test_the_token_replaces_the_placeholder():
    prompt = system_prompt(token="tok-123")
    assert "tok-123" in prompt and PLACEHOLDER not in prompt


def test_without_a_token_a_random_canary_is_used():
    assert PLACEHOLDER not in system_prompt()
