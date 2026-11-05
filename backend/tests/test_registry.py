"""The tool registry: schemas from the params model, and errors returned, never raised."""

from pydantic import BaseModel, ConfigDict, Field

from portfolio_agent.tools.registry import Registry, Tool, ToolResult


class EchoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str = Field(max_length=5)


def echo(args, ctx):
    return ToolResult(args.word, {"seen": args.word}, frozenset({f"x#{args.word}"}))


def boom(args, ctx):
    raise RuntimeError("db down")


ECHO = Tool("echo", "Echo a word.", EchoArgs, echo,
            schema_extra=lambda ctx: {"word": {"enum": ctx}})
REG = Registry.of([ECHO, Tool("boom", "Fails.", EchoArgs, boom)])


def test_schema_is_openai_function_format_with_the_runtime_enum():
    schema = REG.schemas(["hi", "yo"])[0]
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "echo" and fn["description"] == "Echo a word."
    word = fn["parameters"]["properties"]["word"]
    assert word["enum"] == ["hi", "yo"] and word["maxLength"] == 5
    assert "title" not in fn["parameters"] and "title" not in word
    assert fn["parameters"]["additionalProperties"] is False


def test_a_valid_call_returns_both_views_and_the_chunk_ids():
    result = REG.call("echo", '{"word": "hi"}', ["hi"])
    assert result.model_view == "hi" and result.error is None
    assert result.trace_view["seen"] == "hi" and result.trace_view["tool"] == "echo"
    assert isinstance(result.trace_view["duration_ms"], int)
    assert result.chunk_ids == {"x#hi"}


def test_bad_arguments_come_back_as_invalid_args():
    for raw in ['{"word": "toolong"}', '{"word": "hi", "x": 1}', "not json", '{"word": "no"}']:
        result = REG.call("echo", raw, ["hi"])
        assert result.error == "invalid_args" and result.invalid_args, raw
        assert result.chunk_ids == frozenset()
        assert '"error": "invalid_args"' in result.model_view


def test_an_unknown_tool_is_invalid_and_lists_the_real_ones():
    result = REG.call("delete_all", "{}", [])
    assert result.error == "unknown_tool" and result.invalid_args
    assert "echo, boom" in result.model_view


def test_a_failing_handler_is_reported_and_does_not_count_as_invalid():
    result = REG.call("boom", '{"word": "a"}', [])
    assert result.error == "tool_failed" and not result.invalid_args
    assert "db down" in result.model_view
