from skillpulse_crawler.models import WeeklyDigestItem


def test_required_fields():
    item = WeeklyDigestItem(
        section="paper", title="T", url="https://x.com",
        source="arXiv", source_id="2406.12345",
    )
    assert item.id == ""
    assert item.section == "paper"


def test_id_auto_generation_from_source():
    item = WeeklyDigestItem(
        section="paper", title="T", url="https://x.com",
        source="arXiv", source_id="2406.12345",
    )
    item = item.with_generated_id()
    assert item.id.startswith("paper-arXiv-")


def test_invalid_url_rejected():
    import pytest
    with pytest.raises(Exception):
        WeeklyDigestItem(
            section="paper", title="T", url="ftp://bad",
            source="arXiv", source_id="1",
        )