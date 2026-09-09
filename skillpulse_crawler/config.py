from pathlib import Path
import yaml
from .models import SourceConfig


def load_source_config(path: Path) -> SourceConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourceConfig(**data)


def load_all_sources(directory: Path) -> list[SourceConfig]:
    return [
        load_source_config(p)
        for p in sorted(directory.glob("*.yaml"))
        if not p.name.startswith("_")
    ]