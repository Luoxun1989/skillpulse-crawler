from datetime import date, timedelta
from skillpulse_crawler.pipeline.rank import score


def test_recency_decreases_with_age():
    s0 = score(published_date=date.today(), stars=100, comments=0, likes=0)
    s30 = score(published_date=date.today() - timedelta(days=30), stars=100, comments=0, likes=0)
    assert s0 > s30


def test_engagement_increases_with_stars():
    s_low = score(published_date=date.today(), stars=0, comments=0, likes=0)
    s_high = score(published_date=date.today(), stars=10000, comments=0, likes=0)
    assert s_high > s_low


def test_none_date_falls_back():
    s = score(published_date=None, stars=100, comments=10, likes=10)
    assert 0.0 < s < 1.0