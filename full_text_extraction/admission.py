"""Pace request starts independently of concurrent, long-running API responses."""
from math import ceil
from threading import Lock
from time import monotonic, sleep
from typing import Callable
import json

import models
import progress
import prompts
import storage

SECONDS_PER_MINUTE = 60
RATE_LIMIT_UTILIZATION = 0.80
ESTIMATED_CHARACTERS_PER_TOKEN = 3


class RequestPacer:
    """Reserve spaced start times without holding a lock during waits or requests."""

    def __init__(self, tokens_per_minute: int, *, clock: Callable[[], float] = monotonic,
                 pause: Callable[[float], None] = sleep) -> None:
        if tokens_per_minute <= 0:
            raise ValueError('tokens_per_minute must be positive')
        self._tokens_per_second = tokens_per_minute * RATE_LIMIT_UTILIZATION / SECONDS_PER_MINUTE
        self._clock = clock
        self._pause = pause
        self._lock = Lock()
        self._next_start = clock()

    def reserve_delay(self, estimated_tokens: int) -> float:
        if estimated_tokens <= 0:
            raise ValueError('estimated_tokens must be positive')
        with self._lock:
            now = self._clock()
            start = max(now, self._next_start)
            self._next_start = start + estimated_tokens / self._tokens_per_second
        return max(0.0, start - now)

    def wait(self, estimated_tokens: int, source: str | None) -> None:
        delay = self.reserve_delay(estimated_tokens)
        if delay > 0:
            progress.log(f'Pacing request start for {source or "paper"}: waiting {delay:.0f}s.')
            self._pause(delay)


def estimated_request_tokens(settings: storage.Settings, text: str) -> int:
    """Use a conservative character estimate; the server's token accounting wins."""
    schema = json.dumps(models.ExtractionPaper.model_json_schema())
    estimated_input = ceil((len(text) + len(prompts.INSTRUCTIONS) + len(schema)) / ESTIMATED_CHARACTERS_PER_TOKEN)
    return max(settings.max_output_tokens, estimated_input)
