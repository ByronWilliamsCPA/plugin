"""Async HTTP client with exponential backoff retry logic."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 503}


async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> dict[str, Any]:
    """Fetch a URL with exponential backoff retry on 429/503 responses.

    Args:
        client: An httpx.AsyncClient instance.
        url: The URL to fetch.
        max_retries: Maximum number of retry attempts after the first failure.
        base_delay: Initial delay in seconds; doubles on each subsequent retry.

    Returns:
        Parsed JSON response body as a dict.

    Raises:
        httpx.HTTPStatusError: If a non-retryable error status is returned,
            or if max_retries is exhausted on a retryable status.
        httpx.RequestError: If a network-level error occurs.
    """
    delay = base_delay

    for attempt in range(max_retries + 1):
        response = await client.get(url)

        if response.status_code == 200:
            return response.json()  # type: ignore[no-any-return]

        if response.status_code not in RETRYABLE_STATUS_CODES:
            response.raise_for_status()

        if attempt == max_retries:
            response.raise_for_status()

        logger.warning(
            "Retryable %s on attempt %d/%d, retrying in %.1fs",
            response.status_code,
            attempt + 1,
            max_retries,
            delay,
        )
        await asyncio.sleep(delay)
        delay *= 2

    msg = "unreachable"
    raise RuntimeError(msg)  # pragma: no cover
