"""Demo runner: enrich the (dummy/test) OpenAI company + 5 people.

Usage:
  python -m scripts.demo_openai

Set FETCH_PHONE=false in .env to save credits (task says phone = "if available").
"""
import asyncio
import logging

from app.config import get_settings
from app.enricher import Enricher
from app.hubspot_client import HubSpotClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("demo")

DEMO_COMPANY = {"name": "OpenAI (Demo)", "domain": "openai.com"}


async def main():
    settings = get_settings()
    enricher = Enricher(settings)
    hs = HubSpotClient(settings)
    try:
        # 1. create / reuse the demo company
        existing = await hs.find_contact_by_property  # noqa (kept for parity)
        search = await hs._request(
            "POST",
            "/crm/v3/objects/companies/search",
            json={
                "filterGroups": [{"filters": [
                    {"propertyName": "domain", "operator": "EQ", "value": DEMO_COMPANY["domain"]}
                ]}],
                "properties": ["domain", "name"],
                "limit": 1,
            },
        )
        results = (search or {}).get("results", [])
        if results:
            company_id = results[0]["id"]
            log.info("company exists: %s", company_id)
        else:
            company_id = await hs._create_company(DEMO_COMPANY)  # type: ignore[attr-defined]
            log.info("company created: %s", company_id)

        # 2. enrich company
        res = await enricher.enrich_company_by_id(company_id)
        for n in res.notes:
            log.info("[company] %s", n)

        # 3. find + create 5 people (job-title filter from env)
        res = await enricher.find_and_create_contacts(company_id, DEMO_COMPANY["domain"])
        for n in res.notes:
            log.info("[contacts] %s", n)
    finally:
        await enricher.aclose()
        await hs.aclose()


if __name__ == "__main__":
    asyncio.run(main())
