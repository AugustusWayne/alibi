"""Runtime settings.

M0 needs exactly one thing: where FalkorDB is. Everything else arrives with the
milestone that needs it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Immutable, so nothing can retune the connection mid-run."""

    falkor_host: str = "localhost"
    falkor_port: int = 6379

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            falkor_host=os.environ.get("FALKOR_HOST", cls.falkor_host),
            falkor_port=int(os.environ.get("FALKOR_PORT", cls.falkor_port)),
        )


settings = Settings.from_env()
