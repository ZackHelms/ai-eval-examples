"""Tests for scriptfix.stats: the Clopper-Pearson lower bound."""

from __future__ import annotations

import pytest

from scriptfix.stats import lower_bound


@pytest.mark.parametrize(
    ("passes", "n", "expected"),
    [(10, 10, 0.741), (95, 100, 0.898), (99, 100, 0.953), (59, 59, 0.950)],
)
def test_reference_table(passes: int, n: int, expected: float) -> None:
    assert lower_bound(passes, n) == pytest.approx(expected, abs=1e-3)


@pytest.mark.parametrize("n", [1, 10, 100])
def test_zero_passes_is_zero(n: int) -> None:
    assert lower_bound(0, n) == 0.0


def test_no_trials_is_no_evidence() -> None:
    assert lower_bound(0, 0) == 0.0


@pytest.mark.parametrize("n", [1, 5, 59, 1000])
@pytest.mark.parametrize("confidence", [0.9, 0.95, 0.99])
def test_all_passes_matches_closed_form(n: int, confidence: float) -> None:
    assert lower_bound(n, n, confidence) == pytest.approx((1 - confidence) ** (1 / n))


def test_monotonic_in_passes() -> None:
    bounds = [lower_bound(k, 50) for k in range(51)]
    assert bounds == sorted(bounds)
    assert len(set(bounds)) == len(bounds)


def test_higher_confidence_is_lower_bound() -> None:
    assert lower_bound(95, 100, 0.99) < lower_bound(95, 100, 0.95)


def test_large_n_is_stable() -> None:
    # Exact tails must not overflow or underflow at n = 1000.
    bound = lower_bound(990, 1000)
    assert 0.98 < bound < 0.99


@pytest.mark.parametrize(
    ("passes", "n"),
    [(11, 10), (-1, 10), (0, -1), (1, 0)],
)
def test_bad_counts_raise(passes: int, n: int) -> None:
    with pytest.raises(ValueError):
        lower_bound(passes, n)


@pytest.mark.parametrize("confidence", [0, 1, -0.5, 1.5])
def test_bad_confidence_raises(confidence: float) -> None:
    with pytest.raises(ValueError):
        lower_bound(5, 10, confidence)
