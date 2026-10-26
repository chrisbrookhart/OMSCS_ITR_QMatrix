"""Prepare PDF text locally or extract evidence-grounded SLR records with OpenAI."""
import argparse
from pathlib import Path
import sys
import pipeline
import progress
import storage

DEFAULT_LIMIT = 1
EXAMPLES = '''Examples (from check-in-2/):
  uv run full_text_extraction/extract.py
      Prepare one PDF locally; no API calls.
  uv run full_text_extraction/extract.py --execute --model gpt-6.1-sol
      Extract one PDF, reusing a matching completed extraction when available.
  uv run full_text_extraction/extract.py --execute --limit 21 --model gpt-6-luna
      Extract up to 21 PDFs, in sorted relative-path order.
  uv run full_text_extraction/extract.py --execute --resume output/full_text_extraction/<run>
      Continue a run with the same inputs, settings and model.

Each new run writes to OUTPUT/<timestamp>/, including extraction.xlsx,
manifest.json, and per-paper JSON/text. Paper IDs are readable BibTeX-style
citation keys; --source-map preserves existing keys. OUTPUT/cache_v2/ avoids
repeating completed paid requests. Progress is flushed to stdout immediately;
API waits report elapsed time every {heartbeat_seconds} seconds. Default paths are relative
to the project, independent of your current working directory.'''


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, epilog=EXAMPLES.format(heartbeat_seconds=progress.HEARTBEAT_SECONDS),
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--input', type=Path, default=storage.ROOT / 'input/full_text',
                        help='Recursively search this folder for PDFs.\nDefault: %(default)s')
    parser.add_argument('--settings', type=Path, default=storage.PROJECT / storage.SETTINGS_FILE,
                        help='JSON model, reasoning, token, timeout and retry settings.\nDefault: %(default)s')
    parser.add_argument('--limit', type=positive, default=DEFAULT_LIMIT,
                        help='Maximum PDFs to process in sorted path order (default: %(default)s).')
    parser.add_argument('--model', choices=storage.SUPPORTED_MODELS,
                        help='Override the model in --settings; otherwise use its model (bundled default: gpt-6-luna).')
    parser.add_argument('--output', type=Path, default=storage.ROOT / 'output/full_text_extraction',
                        help='Root for timestamped run folders and the shared cache.\nDefault: %(default)s')
    add_execution_arguments(parser)
    return parser


def add_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--execute', action='store_true',
                        help='Send uncached PDF text to OpenAI (paid). Without this flag, only prepare local text.')
    parser.add_argument('--resume', type=Path,
                        help='Existing run folder to continue; requires the same mode, selected PDFs, settings and model.')
    parser.add_argument('--source-map', type=Path,
                        help='Optional JSON array of {source, paper_id} entries preserving bibliography IDs.')
    parser.add_argument('--retry-failed', action='store_true',
                        help='Archive and retry saved incomplete/refused/malformed responses; may incur new API usage.')


def main() -> int:
    parser = get_parser()
    args = parser.parse_args()
    try:
        return pipeline.main(input_directory=args.input.resolve(), settings_path=args.settings,
            limit=args.limit, execute=args.execute, resume=args.resume, output_directory=args.output,
            source_map=args.source_map, retry_failed=args.retry_failed, model=args.model)
    except ValueError as exc:
        parser.error(str(exc))
    return 1


if __name__ == '__main__':
    sys.exit(main())
