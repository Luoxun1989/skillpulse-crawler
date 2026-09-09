from ..models import WeeklyDigestItem
from ..history import History


def filter_new(items, history: History) -> list:
    fresh = []
    for item in items:
        if not history.has_seen(item.section, item.source, item.source_id):
            fresh.append(item)
    return fresh