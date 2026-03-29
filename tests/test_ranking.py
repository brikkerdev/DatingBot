"""Tests for the ranking service calculations."""

from src.services.ranking import calc_combined_score


def test_combined_score_all_zero():
    assert calc_combined_score(0, 0, 0) == 0.0


def test_combined_score_weights():
    # 0.4 * 100 + 0.5 * 100 + 0.1 * 100 = 40 + 50 + 10 = 100
    assert calc_combined_score(100, 100, 100) == 100.0


def test_combined_score_primary_only():
    assert calc_combined_score(50, 0, 0) == 20.0  # 0.4 * 50


def test_combined_score_behavioral_only():
    assert calc_combined_score(0, 80, 0) == 40.0  # 0.5 * 80


def test_combined_score_with_referral():
    result = calc_combined_score(60, 40, 50)
    expected = 0.4 * 60 + 0.5 * 40 + 0.1 * 50  # 24 + 20 + 5 = 49
    assert result == expected
