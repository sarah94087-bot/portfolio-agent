"""The job match report as the visitor keeps it: Markdown, made on the server (US-5.3).

Everything taken from the posting or from a model is escaped, so a posting cannot put a link, an
image or a table row into the file. Both languages' words live here, as the page's do in
dictionaries.ts: the file is written in the language of the page it was asked from.
"""

import re
from typing import Any

LABELS = {
    "he": {
        "title": "דוח התאמה למשרה",
        "agent": "הסוכן של שרה · סוכן AI",
        "overall": "התאמה כוללת",
        "levels": {"high": "התאמה גבוהה", "partial": "התאמה חלקית", "low": "התאמה נמוכה"},
        "strength": {"strong": "חזקה", "partial": "חלקית", "none": "אין עדות"},
        "kind": {"must": "חובה", "nice": "יתרון"},
        "gaps": "פערים",
        "gaps_note": "זה מה שלא נמצא בתיק, לא בהכרח מה שאין לשרה.",
        "no_gaps": "לכל הדרישות נמצאה עדות בתיק.",
        "requirements": "דרישות",
        "columns": ["דרישה", "סוג", "עוצמה", "הנמקה", "מקורות"],
        "cv_only": "מופיע בקורות החיים בלבד",
        "years": "המשרה דורשת {required} שנים. העבודה שצוטטה מכסה {covered}",
        "summary": "סיכום",
        "sources": "מקורות",
        "date": "תאריך",
        "link": "קישור לשיחה",
        "link_note": "נפתח רק בדפדפן שבו הדוח נוצר, עד 30 יום",
        "footer": "דוח אוטומטי שנוצר על ידי סוכן AI מתוך תיק העבודות, לא על ידי שרה.",
    },
    "en": {
        "title": "Job match report",
        "agent": "Sarah's agent · AI agent",
        "overall": "Overall",
        "levels": {"high": "High match", "partial": "Partial match", "low": "Low match"},
        "strength": {"strong": "Strong", "partial": "Partial", "none": "No evidence"},
        "kind": {"must": "Must", "nice": "Nice"},
        "gaps": "Gaps",
        "gaps_note": "This wasn't found in the portfolio, which doesn't mean Sarah lacks it.",
        "no_gaps": "Every requirement has evidence in the portfolio.",
        "requirements": "Requirements",
        "columns": ["Requirement", "Type", "Strength", "Rationale", "Sources"],
        "cv_only": "Appears in the CV only",
        "years": "The posting asks for {required} years. The cited work covers {covered}",
        "summary": "Summary",
        "sources": "Sources",
        "date": "Date",
        "link": "Link to the conversation",
        "link_note": "opens only in the browser that created the report, for up to 30 days",
        "footer": "An automatic report written by an AI agent from the portfolio, not by Sarah.",
    },
}

GLYPH = {"strong": "●", "partial": "◐", "none": "○", "high": "●", "low": "○"}

_SPECIAL = re.compile(r"([\\`*_{}\[\]()<>#+!|~])")
_LINE_START = re.compile(r"^(\s*)(-|\d+\.)(\s)")


def escape(text: str) -> str:
    """One line of plain text: nothing in it can act as Markdown."""
    flat = " ".join(text.split())
    return _LINE_START.sub(r"\1\\\2\3", _SPECIAL.sub(r"\\\1", flat))


def numbering(data: dict[str, Any]) -> dict[str, int]:
    """Source numbers by first citation, as the screen numbers them."""
    out: dict[str, int] = {}
    for r in data["requirements"]:
        for chunk_id in r["evidence"]:
            out.setdefault(chunk_id, len(out) + 1)
    return out


def years_note(r: dict[str, Any], lang: str) -> str:
    return LABELS[lang]["years"].format(required=r["years_required"], covered=r["years_covered"])


def render(data: dict[str, Any], *, lang: str, date: str, link: str,
           sources: list[tuple[str, str]]) -> str:
    """`sources`: (chunk id, title), in any order. A cited chunk with no title shows its id."""
    t = LABELS[lang]
    titles = dict(sources)
    numbers = numbering(data)
    gaps = [r for r in data["requirements"] if r["strength"] == "none"]
    gaps.sort(key=lambda r: r["kind"] != "must")

    lines = [
        f"# {t['title']}: {escape(data['role_title'])}", "",
        f"**{t['overall']}:** {GLYPH[data['overall']] if data['overall'] != 'partial' else '◐'} "
        f"{t['levels'][data['overall']]}  ",
        f"**{t['date']}:** {date}  ",
        f"**{t['link']}:** <{link}> ({t['link_note']})", "",
        f"## {t['gaps']}", "",
    ]
    if gaps:
        lines += [f"- ○ {escape(r['text'])} ({t['kind'][r['kind']]})" for r in gaps]
        lines += ["", t["gaps_note"]]
    else:
        lines.append(t["no_gaps"])

    lines += ["", f"## {t['requirements']}", "",
              "| " + " | ".join(t["columns"]) + " |", "|" + " --- |" * len(t["columns"])]
    for r in data["requirements"]:
        why = escape(r["rationale"])
        if r.get("cv_only"):
            why += f" ({t['cv_only']})"
        if r.get("years_required") is not None:
            why += f" ({years_note(r, lang)})"
        cites = " ".join(f"[{numbers[c]}]" for c in r["evidence"]) or "—"
        lines.append(f"| {escape(r['text'])} | {t['kind'][r['kind']]} | "
                     f"{GLYPH[r['strength']]} {t['strength'][r['strength']]} | {why} | "
                     f"{cites} |")

    lines += ["", f"## {t['summary']}", "", escape(data["summary"]), ""]
    if numbers:
        lines += [f"## {t['sources']}", ""]
        lines += [f"{n}\\. {escape(titles.get(c, c))} (`{c}`)" + "  " for c, n in numbers.items()]
        lines.append("")
    lines += ["---", "", f"{t['agent']}. {t['footer']}", ""]
    return "\n".join(lines)
