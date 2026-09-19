from __future__ import annotations

from typing import Protocol

from prague_housing.models import Listing


class Collector(Protocol):
    name: str

    def collect(self) -> list[Listing]: ...
