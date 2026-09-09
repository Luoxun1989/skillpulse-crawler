from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, raw: str) -> list[dict]:
        """Return list of dicts; each dict has at minimum title and url."""