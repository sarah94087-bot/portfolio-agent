from pathlib import Path

from portfolio_agent.kb_check import PORTFOLIO_DIR, check

PROJECT = """---
id: demo
type: project
title: {{ en: "Demo", he: "דמו" }}
aliases: ["demo"]
period: "2026"
role: "Sole engineer"
tech: [PostgreSQL]
metrics: {metrics}
architecture:
  components: [{{ id: api, label: "API" }}, {{ id: db, label: "DB" }}]
  edges: [{{ from: api, to: db }}]
code_allowed: false
depth: full
answers: ["What did she build?"]
review: {{ approved: {approved}, approved_on: 2026-11-03, publication_check: own-project }}
---

## Problem
p
## Why it was hard
w
## My role
m
## Architecture
a
## Decisions and alternatives
d
## Results
r
"""

SKILLS = """---
id: skills
type: skills
title: { en: "Skills", he: "כישורים" }
skills:
  - { name: PostgreSQL, level: used, evidence: [demo] }
  - { name: Java, level: studied, evidence: [] }
  - { name: Kubernetes, level: listed, evidence: [missing] }
review: { approved: true, approved_on: 2026-11-03 }
---
"""


def write(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / name).write_text(text, encoding="utf-8")


def project(metrics: str = "[]", approved: str = "true") -> str:
    return PROJECT.format(metrics=metrics, approved=approved)


def test_valid_project_passes(tmp_path):
    write(tmp_path, "demo.md", project())
    assert check(tmp_path) == {}


def test_metric_without_how_measured_fails(tmp_path):
    write(tmp_path, "demo.md", project(metrics='[{ label: "latency", before: "1s" }]'))
    assert any("how_measured" in e for e in check(tmp_path)["demo.md"])


def test_unapproved_record_fails(tmp_path):
    write(tmp_path, "demo.md", project(approved="false"))
    assert any("review.approved must be true" in e for e in check(tmp_path)["demo.md"])


def test_missing_and_empty_headings_fail(tmp_path):
    text = project().replace("## Results\nr\n", "").replace("## My role\nm\n", "## My role\n")
    write(tmp_path, "demo.md", text)
    errors = check(tmp_path)["demo.md"]
    assert "missing required heading '## Results'" in errors
    assert "heading '## My role' is empty" in errors


def test_id_must_match_file_name(tmp_path):
    write(tmp_path, "other.md", project())
    assert any("does not match the file name" in e for e in check(tmp_path)["other.md"])


def test_skill_levels_need_matching_evidence(tmp_path):
    write(tmp_path, "demo.md", project())
    write(tmp_path, "skills.md", SKILLS)
    errors = " ".join(check(tmp_path)["skills.md"])
    assert "'Java' is studied but has no evidence" in errors
    assert "'Kubernetes' is listed, so evidence must be empty" in errors


def test_skill_evidence_must_exist(tmp_path):
    write(tmp_path, "demo.md", project())
    write(tmp_path, "skills.md", SKILLS.replace("[demo]", "[nowhere]").split("  - { name: Java")[0]
          + "review: { approved: true, approved_on: 2026-11-03 }\n---\n")
    assert check(tmp_path)["skills.md"] == ["'PostgreSQL' cites 'nowhere', which has no record"]


def test_real_portfolio_passes():
    assert check(PORTFOLIO_DIR) == {}


EXPERIENCE = """---
id: job
type: experience
title: { en: "Engineer", he: "מהנדסת" }
aliases: ["job"]
employer: "Acme"
role: "Engineer"
period: "2026"
projects: [demo]
answers: ["Where did she work?"]
review: { approved: true, approved_on: 2026-11-03, publication_check: employer-ok }
---

## Context
c
## Responsibilities
r
## Projects
p
"""


def test_experience_and_project_link_both_ways(tmp_path):
    write(tmp_path, "demo.md", project().replace('role: "Sole engineer"',
                                                 'experience: job\nrole: "Sole engineer"'))
    write(tmp_path, "job.md", EXPERIENCE)
    assert check(tmp_path) == {}


def test_broken_experience_links_fail(tmp_path):
    write(tmp_path, "demo.md", project().replace('role: "Sole engineer"',
                                                 'experience: elsewhere\nrole: "Sole engineer"'))
    write(tmp_path, "job.md", EXPERIENCE.replace("## Projects\np\n", ""))
    results = check(tmp_path)
    assert results["demo.md"] == ["experience 'elsewhere' has no record"]
    assert "missing required heading '## Projects'" in results["job.md"]
    assert "project 'demo' does not point back at 'job'" in results["job.md"]
