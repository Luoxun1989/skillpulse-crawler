from datetime import date
from math import log


def score(published_date, stars=0, comments=0, likes=0,
          weight_recency=0.6, weight_engagement=0.4,
          max_engagement=18.0) -> float:
    if published_date:
        age_days = max(0, (date.today() - published_date).days)
    else:
        age_days = 365
    recency = 1.0 / (1.0 + age_days)
    engagement = log(1.0 + stars + comments * 2 + likes * 0.5) / log(1.0 + max_engagement)
    return weight_recency * recency + weight_engagement * engagement