from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawNewsItem:
    source: str
    external_id: str
    title: str
    url: str
    published_at: datetime
    body: str | None = None
    raw_payload: dict = field(default_factory=dict)
    instruments_hint: list[str] = field(default_factory=list)


class NewsSource(ABC):
    name: str
    source_weight: float = 0.5

    @abstractmethod
    async def fetch(self) -> list[RawNewsItem]:
        """Vrátí nové zprávy od posledního fetche."""
        ...

    def is_available(self) -> bool:
        """True pokud jsou k dispozici potřebné API klíče."""
        return True
