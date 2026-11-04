from types import SimpleNamespace

import pytest

from portfolio_agent.ingest import load
from portfolio_agent.retrieval.query import name_pattern, owner_names, strip_names

NAMES = ("Sarah", "Halevy", "שרה", "הלוי")
P = name_pattern(NAMES)


@pytest.mark.parametrize("query, expected", [
    ("Sarah Halevy Docker", "Docker"),
    ("Sarah Halevy C# experience", "C# experience"),
    ("Sarah's Kafka projects", "Kafka projects"),
    ("sarah halevy's plant health model accuracy", "plant health model accuracy"),
    ("images stored in Sarah Halevy's portfolio", "images stored in portfolio"),
    ("weed detector picture capture time", "weed detector picture capture time"),
    ("ניסיון של שרה הלוי בדוקר", "ניסיון של בדוקר"),
    ("לשרה יש ניסיון ב-Kafka?", "יש ניסיון ב-Kafka?"),
])
def test_strip_names_removes_every_form_of_the_name(query, expected):
    assert strip_names(query, P) == expected


def test_strip_names_keeps_words_that_only_contain_the_name():
    assert strip_names("Sarahville Halevyan", P) == "Sarahville Halevyan"
    assert strip_names("משרהלוי", P) == "משרהלוי"


def test_a_query_that_is_only_the_name_is_kept():
    assert strip_names("Sarah Halevy", P) == "Sarah Halevy"


def test_owner_names_come_from_the_profile_record():
    name = SimpleNamespace(en="Sarah Halevy", he="שרה הלוי")
    profile = SimpleNamespace(type="profile", name=name)
    assert owner_names([SimpleNamespace(type="project"), profile]) == NAMES
    with pytest.raises(ValueError):
        owner_names([SimpleNamespace(type="project")])


def test_the_real_knowledge_base_has_the_name():
    assert owner_names(d.record for d in load()) == NAMES
