"""Runtime settings.

Where FalkorDB is, and — since M4 — where the LLM replay cache lives, which
model the detective runs on and how many calls one case may make. The cap is
here rather than in the loop because it is a deployment decision: it bounds
what a runaway investigation can spend against a live API (project rules,
rule 9).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Immutable, so nothing can retune the connection mid-run."""

    falkor_host: str = "localhost"
    falkor_port: int = 6379

    # SQLite, for the replay cache and eval metadata only — never graph state
    # (spec 3). Gitignored: a recorded run is local, not a committed artifact.
    llm_cache_path: str = "var/llm_cache.sqlite3"
    # No model id and no vendor SDK are named anywhere in this repo. Both the
    # model and the transport that reaches it are deployment settings: set
    # ALIBI_DETECTIVE_MODEL to the id your provider expects, and
    # ALIBI_COMPLETER to a "package.module:factory" returning the callable
    # that performs one request. Scripted and replayed runs need neither.
    detective_model: str = ""
    completer: str = ""
    llm_call_cap: int = 24

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            falkor_host=os.environ.get("FALKOR_HOST", cls.falkor_host),
            falkor_port=int(os.environ.get("FALKOR_PORT", cls.falkor_port)),
            llm_cache_path=os.environ.get("ALIBI_LLM_CACHE", cls.llm_cache_path),
            detective_model=os.environ.get("ALIBI_DETECTIVE_MODEL", cls.detective_model),
            completer=os.environ.get("ALIBI_COMPLETER", cls.completer),
            llm_call_cap=int(os.environ.get("ALIBI_LLM_CALL_CAP", cls.llm_call_cap)),
        )


settings = Settings.from_env()
