"""Flushed stdout progress and a heartbeat during blocking API requests."""
from contextlib import contextmanager
from datetime import datetime
from threading import Event, Thread
from time import monotonic
from typing import Iterator

HEARTBEAT_SECONDS = 15
TIMESTAMP_FORMAT = '%H:%M:%S'


def log(message: str) -> None:
    print(f'[{datetime.now().strftime(TIMESTAMP_FORMAT)}] {message}', flush=True)


def report_wait(finished: Event, model: str, started: float) -> None:
    while not finished.wait(HEARTBEAT_SECONDS):
        elapsed = monotonic() - started
        log(f'Still waiting for {model}: {elapsed:.0f}s elapsed (including any API retries).')


@contextmanager
def waiting_for_response(model: str, source: str | None = None) -> Iterator[None]:
    finished = Event()
    label = f'{model} ({source})' if source else model
    worker = Thread(target=report_wait, args=(finished, label, monotonic()), daemon=True)
    worker.start()
    try:
        yield
    finally:
        # Stop immediately on success, failure or interruption; no lingering output.
        finished.set()
        worker.join()
