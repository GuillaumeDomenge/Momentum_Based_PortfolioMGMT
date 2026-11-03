from pathlib import Path

import yaml


def load_config(path: str | Path = "config.yaml") -> dict:
    """Load the single source of truth for a research run."""
    with Path(path).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)
