import json

import publish_quality


def test_committed_page_data_matches_the_result_files():
    # /quality shows only numbers that can be traced to evals/results.
    committed = json.loads(publish_quality.OUTPUT.read_text(encoding="utf-8"))
    assert committed == publish_quality.build(), "run evals/publish_quality.py and commit the file"


def test_passed_follows_the_threshold():
    for row in publish_quality.build()["scorecard"]:
        expected = None if row["threshold"] is None else row["mean"] >= row["threshold"]
        assert row["passed"] == expected
