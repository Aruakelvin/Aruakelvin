from .base import Source
from .defillama import DefiLlamaSource
from .merkl import MerklSource

REGISTRY: dict[str, type[Source]] = {
    DefiLlamaSource.name: DefiLlamaSource,
    MerklSource.name: MerklSource,
}

__all__ = ["REGISTRY", "Source", "DefiLlamaSource", "MerklSource"]
