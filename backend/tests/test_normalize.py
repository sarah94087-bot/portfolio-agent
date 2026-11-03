from portfolio_agent.retrieval.normalize import normalize


def test_final_letters_become_regular_letters():
    assert normalize("ךםןףץ") == "כמנפצ"
    assert normalize("תרגום") == normalize("תרגומ")


def test_niqqud_and_cantillation_are_removed():
    assert normalize("שָׁלוֹם") == "שלומ"
    assert normalize("בְּרֵאשִׁ֖ית") == "בראשית"


def test_presentation_forms_are_split_before_the_marks_go():
    assert normalize("שׁ") == "ש"  # שׁ as one code point


def test_english_is_only_lowercased():
    assert normalize("Human-gated RLS, pgvector & Next.js") == "human-gated rls, pgvector & next.js"
    assert normalize("café") == "café"
