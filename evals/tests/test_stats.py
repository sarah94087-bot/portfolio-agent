import pytest

from stats import format_rate, paired_bootstrap, wilson


def test_wilson_matches_the_example_in_the_spec():
    # docs/03-evaluation-methodology.md, section 5: 57/60 can be anything from 86% to 98%.
    low, high = wilson(57, 60)
    assert low == pytest.approx(0.8630, abs=1e-4)
    assert high == pytest.approx(0.9829, abs=1e-4)


def test_wilson_stays_inside_zero_and_one_at_the_edges():
    low, high = wilson(0, 10)
    assert low == 0.0
    assert high == pytest.approx(0.2775, abs=1e-4)
    low, high = wilson(10, 10)
    assert low == pytest.approx(0.7225, abs=1e-4)
    assert high == 1.0


def test_wilson_narrows_as_the_set_grows():
    small = wilson(17, 20)
    large = wilson(85, 100)
    assert large[1] - large[0] < small[1] - small[0]


@pytest.mark.parametrize("successes, n", [(0, 0), (-1, 10), (11, 10)])
def test_wilson_rejects_impossible_counts(successes, n):
    with pytest.raises(ValueError):
        wilson(successes, n)


def test_format_rate_shows_the_count_next_to_the_percentage():
    assert format_rate(57, 60) == "57/60 (95%) [86%, 98%]"


def test_identical_methods_are_not_significant():
    scores = [1, 0, 1, 1, 0.5] * 17
    d = paired_bootstrap(scores, scores)
    assert (d.mean, d.low, d.high) == (0, 0, 0)
    assert not d.significant


def test_a_clear_improvement_is_significant_and_positive_means_b_is_better():
    a = [0] * 60 + [1] * 25
    b = [1] * 85
    d = paired_bootstrap(a, b)
    assert d.mean == pytest.approx(60 / 85)
    assert d.low > 0
    assert d.significant
    assert paired_bootstrap(b, a).high < 0


def test_one_question_out_of_twenty_is_noise():
    a = [1] * 19 + [0]
    b = [1] * 20
    d = paired_bootstrap(a, b)
    assert d.mean == pytest.approx(0.05)
    assert d.low == 0
    assert not d.significant


def test_the_pairing_finds_what_two_separate_rates_miss():
    # b fixes 8 questions that a got wrong and breaks none. As two separate rates, 30/60 and
    # 38/60 have overlapping intervals; question by question, b is never worse.
    a = [1, 0] * 30
    b = [1] * 16 + [1, 0] * 22
    assert (sum(a), sum(b)) == (30, 38)
    assert all(y >= x for x, y in zip(a, b, strict=True))
    assert wilson(38, 60)[0] < wilson(30, 60)[1]
    d = paired_bootstrap(a, b)
    assert d.low > 0
    assert d.significant


def test_different_failures_at_the_same_rate_are_no_difference():
    a = [1, 0] * 40
    b = [0, 1] * 40
    d = paired_bootstrap(a, b)
    assert d.mean == 0
    assert not d.significant


def test_same_seed_same_interval():
    a = [1, 0, 1, 0.5, 0, 1, 1, 0] * 10
    b = [1, 1, 1, 0.5, 0, 1, 0, 1] * 10
    assert paired_bootstrap(a, b, seed=7) == paired_bootstrap(a, b, seed=7)


def test_bootstrap_rejects_unpaired_or_empty_scores():
    with pytest.raises(ValueError):
        paired_bootstrap([1, 0], [1])
    with pytest.raises(ValueError):
        paired_bootstrap([], [])
