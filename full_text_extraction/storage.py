"""Atomic persistence, explicit configuration and stable source associations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
from typing import TypeAlias
from pydantic import BaseModel, ConfigDict

JsonValue: TypeAlias = None | bool | int | float | str | list['JsonValue'] | dict[str, 'JsonValue']
PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parent
CONFIG_FILE = 'config.py'
API_KEY_NAME = 'OPENAI_API_KEY'
SETTINGS_FILE = 'settings.json'
MANIFEST_FILE = 'manifest.json'
RECORD_FILE = 'extraction.json'
RESPONSE_FILE = 'response.json'
PAGES_FILE = 'pages.json'
TEXT_FILE = 'paper.txt'
WORKBOOK_FILE = 'extraction.xlsx'
SCHEMA_FILE = 'schema.json'
PROMPT_FILE = 'instructions.txt'
CACHE_DIRECTORY = 'cache_v2'
SPARSE_PAGE_CHARACTERS = 100
SUPPORTED_MODELS = ('gpt-6-luna', 'gpt-6-sol', 'gpt-6.1-sol')


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str
    reasoning_effort: str
    max_output_tokens: int
    max_input_characters: int
    timeout_seconds: float
    max_retries: int = 2


class SourceAssociation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: str
    paper_id: str


def write_json(path: Path, data: JsonValue | BaseModel) -> None:
    """Replace atomically so interruptions cannot leave a truncated checkpoint."""
    serialized = data.model_dump_json(indent=2) if isinstance(data, BaseModel) else json.dumps(data, ensure_ascii=False, indent=2)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(serialized + '\n', encoding='utf-8')
    temporary.replace(path)


def load_settings(path: Path, *, model: str | None = None) -> Settings:
    settings = Settings.model_validate_json(path.read_text(encoding='utf-8'))
    if model is not None:
        if model not in SUPPORTED_MODELS:
            raise ValueError(f'Model must be one of: {", ".join(SUPPORTED_MODELS)}')
        settings = settings.model_copy(update={'model': model})
    if min(settings.max_output_tokens, settings.max_input_characters, settings.timeout_seconds) <= 0:
        raise ValueError('Token, character and timeout limits must be positive')
    if settings.max_retries < 0:
        raise ValueError('max_retries must be nonnegative')
    return settings


def load_api_key() -> str:
    path = PROJECT / CONFIG_FILE
    if not path.is_file():
        raise ValueError(f'Copy {CONFIG_FILE}.template to {CONFIG_FILE} and set {API_KEY_NAME}')
    key = runpy.run_path(str(path)).get(API_KEY_NAME)
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f'Set a nonempty {API_KEY_NAME} in {path}')
    return key.strip()


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fingerprint(data: JsonValue) -> str:
    return digest_bytes(json.dumps(data, sort_keys=True, ensure_ascii=False).encode())


def load_associations(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    entries = [SourceAssociation.model_validate(item) for item in json.loads(path.read_text())]
    sources = [entry.source for entry in entries]
    if len(sources) != len(set(sources)) or any(not e.paper_id.strip() for e in entries):
        raise ValueError('Source map needs unique relative source paths and nonempty paper IDs')
    return {entry.source: entry.paper_id for entry in entries}
