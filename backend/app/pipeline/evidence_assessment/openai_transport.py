"""Bounded OpenAI transport recovery, with content-free operational diagnostics."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
import random
import re

import httpx


MAX_ATTEMPTS = 3
MIN_RETRY_SECONDS = 20
CONNECT_SECONDS = 15
logger = logging.getLogger(__name__)

QUOTA_CODES = {
    'insufficient_quota', 'quota_exceeded', 'billing_hard_limit_reached',
    'billing_not_active', 'organization_spend_limit_exceeded',
    'project_spend_limit_exceeded', 'organization_usage_limit_exceeded',
}
ERROR_CODES = QUOTA_CODES | {
    'invalid_json_schema', 'model_not_found', 'invalid_api_key',
    'rate_limit_exceeded', 'slow_down', 'server_is_overloaded', 'server_error',
    'internal_server_error', 'service_unavailable', 'context_length_exceeded',
    'invalid_request_error',
}
ERROR_TYPES = {
    'invalid_request_error', 'authentication_error', 'permission_error',
    'rate_limit_error', 'insufficient_quota', 'server_error', 'service_unavailable_error',
}
EXCEPTION_TYPES = {
    'ConnectError', 'ConnectTimeout', 'ReadError', 'ReadTimeout', 'WriteError',
    'WriteTimeout', 'RemoteProtocolError', 'PoolTimeout', 'TimeoutException',
    'RequestError', 'HTTPError',
}
PHASES = {'research_response', 'research_recovery_response', 'assessment_response'}
TRANSIENT_ERRORS = (
    httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError, httpx.ReadTimeout,
    httpx.WriteError, httpx.WriteTimeout, httpx.RemoteProtocolError, httpx.PoolTimeout,
)


def error_metadata(response):
    """Do not retain provider messages, arbitrary fields, request bodies or keys."""
    try:
        body = response.json()
    except ValueError:
        return {}
    error = body.get('error') if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return {}
    result = {}
    for field, choices in (('code', ERROR_CODES), ('type', ERROR_TYPES)):
        value = error.get(field)
        if value is not None:
            result['error_' + field] = value if isinstance(value, str) and value in choices else 'other'
    return result


def quota_error(metadata):
    return metadata.get('error_code') in QUOTA_CODES or metadata.get('error_type') == 'insufficient_quota'


def _transient(response, metadata):
    if quota_error(metadata):
        return False
    if response.status_code in {408, 409, 429} or response.status_code >= 500:
        return True
    # A Responses job may report a server failure inside a successful HTTP envelope.
    if response.status_code == 200:
        return metadata.get('error_code') in {
            'server_error', 'internal_server_error', 'service_unavailable', 'server_is_overloaded',
            'rate_limit_exceeded', 'slow_down',
        }
    return False


def _retry_after(response):
    if response is None:
        return 0.0
    delays = []
    for name, divisor in (('retry-after-ms', 1000), ('retry-after', 1)):
        raw = response.headers.get(name)
        if raw is None:
            continue
        try:
            delay = float(raw) / divisor
        except (ValueError, OverflowError):
            if name != 'retry-after':
                continue
            try:
                when = parsedate_to_datetime(raw)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                delay = (when - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                continue
        if math.isfinite(delay) and delay >= 0:
            delays.append(delay)
    return max(delays, default=0.0)


async def _sleep(seconds):
    await asyncio.sleep(seconds)


def _record(trace, event):
    event = {key: value for key, value in event.items() if value is not None}
    if trace is not None:
        # RetrievalTrace's public contract is dict[str, str].
        trace.decisions.append({'decision': 'openai_transport',
                                **{key: str(value) for key, value in event.items()}})
    logger.log(logging.INFO if event['outcome'] == 'success' else logging.WARNING,
               'OpenAI transport %s', json.dumps(event, sort_keys=True))


async def post_with_retries(client, payload, *, deadline, phase, trace=None, reserve_retry=None):
    """Retry this stage only; all attempts and waits share the caller's deadline.

    reserve_retry conservatively accounts for potentially executed research on
    an ambiguous failure. A retry cannot silently multiply the web-action grant.
    No retry is made for a rejected schema, authentication or exhausted credits.
    """
    if phase not in PHASES:
        raise ValueError('Unknown OpenAI request phase')
    loop = asyncio.get_running_loop()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        left = deadline - loop.time()
        if left <= 0:
            raise TimeoutError()
        started = loop.time()
        response, failure = None, None
        event = {'provider': 'openai', 'phase': phase, 'attempt': attempt}
        try:
            response = await client.post('/v1/responses', json=payload,
                timeout=httpx.Timeout(min(120.0, left), connect=min(CONNECT_SECONDS, left)))
            metadata = error_metadata(response)
            event.update(http_status=response.status_code, **metadata)
            request_id = response.headers.get('x-request-id', '')
            if re.fullmatch(r'req_[A-Za-z0-9_-]{1,100}', request_id):
                event['request_id'] = request_id
            retryable = _transient(response, metadata)
            # HTTP429 rejects work before execution; other failures can be ambiguous.
            ambiguous = response.status_code != 429
        except httpx.RequestError as error:
            failure = error
            kind = type(error).__name__
            event['exception_type'] = kind if kind in EXCEPTION_TYPES else 'other'
            retryable = isinstance(error, TRANSIENT_ERRORS)
            ambiguous = not isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout))
        except asyncio.CancelledError:
            if loop.time() >= deadline:
                _record(trace, {**event, 'outcome': 'failed', 'stop_reason': 'deadline',
                    'exception_type': 'TimeoutException',
                    'elapsed_ms': round((loop.time() - started) * 1000)})
            raise
        event['elapsed_ms'] = round((loop.time() - started) * 1000)
        if response is not None and response.status_code == 200 and not event.get('error_code') and not event.get('error_type'):
            _record(trace, {**event, 'outcome': 'success'})
            return response
        delay = max(_retry_after(response), 2 ** (attempt - 1) + random.uniform(0, .25))
        stop = ('non_retryable' if not retryable else
                'attempt_limit' if attempt == MAX_ATTEMPTS else
                'deadline' if deadline - loop.time() < delay + MIN_RETRY_SECONDS else None)
        if stop is None and ambiguous and reserve_retry is not None:
            replacement = reserve_retry(payload)
            if replacement is None:
                stop = 'search_budget'
            else:
                payload = replacement
        if stop is not None:
            _record(trace, {**event, 'outcome': 'failed', 'stop_reason': stop})
            if failure is not None:
                raise failure
            return response
        _record(trace, {**event, 'outcome': 'retry', 'retry_delay_ms': round(delay * 1000)})
        if response is not None:
            await response.aclose()
        await _sleep(delay)
