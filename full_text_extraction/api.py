"""One strict structured request; retain the response before parsing or validation."""
from contextlib import closing
from pathlib import Path
from openai import OpenAI
from openai.types.responses import Response
import models
import admission
import prompts
import progress
import storage

RESPONSE_SCHEMA_NAME = 'slr_paper'
COMPLETED_STATUS = 'completed'


def create_client(settings: storage.Settings) -> OpenAI:
    return OpenAI(api_key=storage.load_api_key(), timeout=settings.timeout_seconds,
                  max_retries=settings.max_retries)


def request_response(client: OpenAI, settings: storage.Settings, text: str) -> Response:
    return client.responses.create(
        model=settings.model, reasoning={'effort': settings.reasoning_effort},
        max_output_tokens=settings.max_output_tokens, store=False,
        instructions=prompts.INSTRUCTIONS, input=text,
        text={'format': {'type': 'json_schema', 'name': RESPONSE_SCHEMA_NAME,
                         'strict': True, 'schema': models.ExtractionPaper.model_json_schema()}})


def request_paper(settings: storage.Settings, text: str, folder: Path,
                  source: str | None = None, pacer: admission.RequestPacer | None = None) -> models.ExtractionPaper:
    if pacer is not None:
        pacer.wait(admission.estimated_request_tokens(settings, text), source)
    progress.log(f'Requesting extraction from {settings.model}; waiting for the API response...')
    with closing(create_client(settings)) as client, progress.waiting_for_response(settings.model, source):
        response = request_response(client, settings, text)
        # Preserve paid output before closing the client or checking completion.
        storage.write_json(folder / storage.RESPONSE_FILE, response.model_dump(mode='json'))
    progress.log('API response saved; checking completion and validating structured output.')
    if response.status != COMPLETED_STATUS or not response.output_text:
        details = response.incomplete_details
        reason = details.reason if details is not None else response.status
        raise ValueError(f'Incomplete/refused response ({reason}) retained in response.json; inspect before retrying')
    return models.ExtractionPaper.model_validate_json(response.output_text)
