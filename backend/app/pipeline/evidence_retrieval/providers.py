"""Bounded provider calls. Keys only go to their own provider's HTTPS endpoint."""

import asyncio

import httpx

from .sources import SOURCES


REQUEST_TIMEOUT_SECONDS = 20.0


async def request_json(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> dict:
    async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
        response = await client.request(method, url, **kwargs)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict) or "error" in value:
            raise ValueError("Invalid provider response")
        return value


async def google_search(client: httpx.AsyncClient, query: str, key: str) -> list[dict]:
    data = await request_json(client, "GET",
        "https://factchecktools.googleapis.com/v1alpha1/claims:search",
        headers={"X-Goog-Api-Key": key},
        params={"query": query, "languageCode": "en", "pageSize": 5})
    # Google omits the repeated claims field on a successful empty response.
    claims = data.get("claims", [])
    if not isinstance(claims, list) or any(not isinstance(item, dict) for item in claims):
        raise ValueError("Invalid claims list")
    return claims[:5]


async def tavily_extract(client: httpx.AsyncClient, urls: list[str], key: str, *, format: str = "text") -> dict:
    data = await request_json(client, "POST", "https://api.tavily.com/extract",
        headers={"Authorization": f"Bearer {key}"},
        json={"urls": urls, "extract_depth": "basic", "format": format, "timeout": 15})
    if not isinstance(data.get("results"), list) or not isinstance(data.get("failed_results", []), list):
        raise ValueError("Invalid extraction response")
    return data


async def tavily_search(client: httpx.AsyncClient, query: str, key: str, *, broad: bool = False) -> list[dict]:
    data = await request_json(client, "POST", "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {key}"},
        json={"query": query, "search_depth": "advanced", "max_results": 8,
              "chunks_per_source": 3, "topic": "general", "include_answer": False,
              "include_raw_content": False, "include_images": False,
              "auto_parameters": False, **({} if broad else {"include_domains": list(SOURCES)})})
    results = data.get("results")
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        raise ValueError("Invalid search results")
    return results[:8]
