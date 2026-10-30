"""Read local filename-to-Drive links without contacting Google Drive."""
from collections.abc import Mapping
from pathlib import Path
from pydantic import TypeAdapter
import storage

LINKS_FILENAME = 'pdf_drive_links.json'
DEFAULT_LINKS_PATH = storage.ROOT / 'input' / LINKS_FILENAME


def load_links(path: Path | None = None) -> dict[str, str]:
    selected = path if path is not None else DEFAULT_LINKS_PATH
    if path is None and not selected.exists():
        return {}
    return TypeAdapter(dict[str, str]).validate_json(selected.read_text(encoding='utf-8'), strict=True)


def for_source(links: Mapping[str, str], source: str) -> str | None:
    """Prefer an exact relative source path, then the mapping's filename key."""
    return links.get(source) or links.get(Path(source).name)
