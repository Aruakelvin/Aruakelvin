"""Source plugin interface.

A source fetches raw data from one provider and yields normalized
:class:`~incentive_analyzer.models.Opportunity` objects. To add a new provider,
subclass :class:`Source`, implement :meth:`fetch`, and register it in
``incentive_analyzer.sources.REGISTRY``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from ..http import HttpClient
from ..models import Opportunity


class Source(ABC):
    name: str = "base"
    description: str = ""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    @abstractmethod
    def fetch(self) -> Iterable[Opportunity]:
        """Return every incentivized opportunity this source knows about."""
