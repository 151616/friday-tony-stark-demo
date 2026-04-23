from .classifier import classify_domains
from .domains import ALWAYS_LOADED_DOMAINS, DOMAINS, OPTIONAL_DOMAINS


def __getattr__(name: str):
    if name == "LocalDomainToolPool":
        from .pool import LocalDomainToolPool

        return LocalDomainToolPool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ALWAYS_LOADED_DOMAINS",
    "DOMAINS",
    "OPTIONAL_DOMAINS",
    "LocalDomainToolPool",
    "classify_domains",
]
