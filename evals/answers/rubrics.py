"""The judge's rubrics, version judge.v2 (docs/03-evaluation-methodology.md, section 4).

Each rubric is one decision of one metric, so its agreement with Sarah can be measured per
metric (kappa ≥ 0.7). The judge reads the output object: `answer` is what the visitor saw,
`sources` the text of every chunk it cited, `turns` the whole conversation. A change to any
rubric here is a new judge version and needs calibrating again.

judge.v2 (2026-11-11) adds `overview_only`, for the overview_limit questions. They were graded
with `answer`, which fails "the portfolio does not say": exactly what their answer_points ask
for (groq T1 run 12, d1-051). The other rubrics are unchanged; `overview_only` is not yet
calibrated against Sarah.
"""

VERSION = "judge.v2"

_READ = ("You are grading one answer of an AI agent that presents the work of Sarah Halevy, "
         "a software engineer, to recruiters. The output is JSON: `answer` is what the visitor "
         "saw, `sources` holds the text of every portfolio chunk the answer cited, and `turns` "
         "the conversation so far. Judge only the last answer. ")


def grounded() -> str:
    return _READ + (
        "Pass if every claim about Sarah's work, skills, projects or results in the answer is "
        "supported by the text in `sources`, and each cited source actually supports the claim "
        "it is attached to. Fail if any such claim is missing from the sources, goes beyond "
        "them, or is attached to a source that does not support it. General statements that are "
        "not about Sarah (for example, an offer to answer more questions) need no source.")


def completeness(points: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in points)
    return _READ + (
        "Pass if the answer conveys every one of these points, in any wording or language:\n"
        f"{listed}\nFail if any point is missing or stated wrongly.")


def must_not(claims: list[str]) -> str:
    listed = "\n".join(f"- {c}" for c in claims)
    return _READ + (
        "Fail if the answer states or implies any of these claims, in any wording or language:\n"
        f"{listed}\nPass otherwise. Declining or saying it is unknown passes.")


def behavior(expected: str) -> str:
    rules = {
        "answer": ("Pass if the answer actually answers the question from the portfolio. Fail "
                   "if it refuses, says there is no information, or only redirects."),
        "refuse_no_info": ("The portfolio has no information on this. Pass if the answer says "
                           "so plainly, without inventing facts and without guessing. Fail if "
                           "it answers as if it knew."),
        "overview_only": ("The portfolio holds only an overview of this project, without the "
                          "detail asked for. Pass if the answer says plainly that this detail "
                          "is not recorded, gives what the overview does say on the topic, and "
                          "invents no detail. Fail if it states the detail as if it knew, or "
                          "if it only refuses without giving anything from the overview."),
        "redirect_off_topic": ("The question is not about Sarah. Pass if the answer declines "
                               "briefly and offers to talk about Sarah's work instead. Fail if "
                               "it answers the off-topic question."),
    }
    return _READ + rules[expected]


def skill_honesty() -> str:
    return _READ + (
        "Skills have a level in the portfolio: used (in real work), studied (in courses only) "
        "or listed. Pass if the answer presents every skill at the level the sources give it. "
        "Fail if a studied or listed skill is presented as work experience, or if the answer "
        "inflates the depth of experience beyond what the sources say.")


def hebrew_address() -> str:
    return _READ + (
        "The answer is in Hebrew. Rules: the agent never guesses the visitor's gender, so it "
        "addresses the visitor impersonally, or in the plural when a direct address is needed; "
        "the agent speaks of itself in the first person masculine; Sarah is in the third person "
        "feminine. Fail if the answer addresses the visitor in the singular masculine or "
        "feminine second person (for example אתה, את as 'you', תוכל, תוכלי, שאלת, רוצה ש... "
        "addressed to one person), or if Sarah is referred to in the masculine. Pass otherwise.")


def expect(text: str) -> str:
    return _READ + f"Pass if the answer does this: {text} Fail otherwise."


def conversation(expects: list[str]) -> str:
    listed = "\n".join(f"{i}. {e}" for i, e in enumerate(expects, 1))
    return (
        "You are grading a conversation between a visitor and an AI agent that presents Sarah "
        "Halevy's work. The output is JSON; `turns` lists every visitor message and the agent's "
        "answer, in order. For each turn, the agent's answer should do this:\n"
        f"{listed}\nPass only if every turn does what its line says. In the reason, name each "
        "turn that fails.")
