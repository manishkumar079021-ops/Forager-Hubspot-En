"""Thin, defensive client for the Forager public API (api-v2.forager.ai).

Auth: `X-API-KEY` header. Docs: https://docs.forager.ai/openapi
All methods return plain dicts/lists and never raise — missing data -> None.
"""
import asyncio
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import Settings

log = logging.getLogger("forager")


class ForagerClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.forager_base_url,
            headers={"X-API-KEY": settings.forager_api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
        )
        # simple concurrency guard so we never hammer the API
        self._sem = asyncio.Semaphore(4)

    async def aclose(self):
        await self._client.aclose()

    # ------------------------------------------------------------------ core
    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TransportError,)),
        reraise=False,
    )
    async def _post(self, path: str, payload: dict) -> dict | None:
        async with self._sem:
            try:
                resp = await self._client.post(path, json=payload)
                if resp.status_code in (401, 403, 404, 422):
                    log.warning("Forager %s -> %s: %s", path, resp.status_code, resp.text[:300])
                    return None
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                log.warning("Forager %s -> %s: %s", path, exc.response.status_code, exc.response.text[:300])
                return None
            except Exception as exc:  # network issues -> retried by tenacity
                log.warning("Forager %s failed: %s", path, exc)
                raise

    # --------------------------------------------------------------- company
    async def enrich_company(self, domain: str) -> dict | None:
        """Best-effort company enrichment by domain (1 credit)."""
        data = await self._post(
            "/datastorage/organization_detail_lookup/",
            {"domain": domain},
        )
        if not data:
            # fallback: search organizations by domain
            data = await self._post(
                "/datastorage/organization_search/",
                {"organization_domains": [domain], "page": 0},
            )
        if not data:
            return None
        org = data.get("organization") or data.get("organizations") or data
        if isinstance(org, list):
            org = org[0] if org else None
        return org or None

    # --------------------------------------------------------------- people
    async def find_people_at_company(
        self, domain: str, job_title: str | None = None, page: int = 0
    ) -> list[dict]:
        """Person Role Search — 1 credit. Filters by company domain + job title."""
        payload: dict = {
            "organization_domains": [domain],
            "role_is_current": True,
            "page": page,
        }
        if job_title:
            payload["role_title"] = job_title  # boolean text search query
        data = await self._post("/datastorage/person_role_search/", payload)
        if not data:
            return []
        return data.get("search_results") or []

    async def person_detail(self, linkedin_public_identifier: str) -> dict | None:
        """Full profile: headline, description, location, roles etc. (1 credit)."""
        data = await self._post(
            "/datastorage/person_detail_lookup/",
            {"linkedin_public_identifier": linkedin_public_identifier},
        )
        if not data:
            return None
        return data.get("person") or data

    async def _contact_lookup(self, kind: str, linkedin_public_identifier: str) -> list | None:
        """Work-email / phone lookups. These endpoints return an async job that
        must be polled, OR inline results depending on the plan — handle both."""
        path = f"/datastorage/person_contacts_lookup/{kind}/"
        data = await self._post(path, {"linkedin_public_identifier": linkedin_public_identifier})
        if not data:
            return None
        results = data.get("results") or data.get("emails") or data.get("phone_numbers")
        if results is not None:
            return results
        job_id = data.get("job_id") or data.get("id")
        if not job_id:
            return None
        # poll the job
        for _ in range(10):
            await asyncio.sleep(3)
            status = await self._post(f"{path}{job_id}/", {})
            if not status:
                return None
            if status.get("status") in ("pending", "running", "started"):
                continue
            return status.get("results") or status.get("emails") or status.get("phone_numbers")
        return None

    async def work_email(self, linkedin_public_identifier: str) -> str | None:
        results = await self._contact_lookup("work_emails", linkedin_public_identifier)
        if results:
            first = results[0]
            return first.get("email") or first.get("address") or None
        return None

    async def phone_number(self, linkedin_public_identifier: str) -> str | None:
        results = await self._contact_lookup("phone_numbers", linkedin_public_identifier)
        if results:
            first = results[0]
            return first.get("phone_number") or first.get("number") or first.get("e164") or None
        return None
