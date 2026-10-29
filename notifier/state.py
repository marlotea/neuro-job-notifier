"""Remember which jobs we've already handled, in state/seen.json.

File format:
    {
      "seeded_sources": ["simplify"],
      "seen_ids": ["simplify:54c83f6c-...", ...]
    }

"seeded_sources" lists each source that has had its first-run seed. The first
time a source works, we mark all its current jobs as seen and send nothing. So
adding a new source later won't flood the inbox with its whole backlog.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "state" / "seen.json"


@dataclass
class State:
    seen_ids: set[str] = field(default_factory=set)
    seeded_sources: set[str] = field(default_factory=set)


def load(path: Path = DEFAULT_PATH) -> State:
    if not path.exists():
        return State()
    data = json.loads(path.read_text() or "{}")
    if isinstance(data, list):
        # Plain list of IDs (the simplest format). Treat every source that
        # appears in it as already seeded.
        ids = set(data)
        return State(seen_ids=ids, seeded_sources={i.split(":", 1)[0] for i in ids})
    return State(
        seen_ids=set(data.get("seen_ids", [])),
        seeded_sources=set(data.get("seeded_sources", [])),
    )


def save(state: State, path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sorted, so the file changes as little as possible between runs and the
    # git diffs stay readable.
    data = {
        "seeded_sources": sorted(state.seeded_sources),
        "seen_ids": sorted(state.seen_ids),
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
