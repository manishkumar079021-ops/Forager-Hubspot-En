"""Core enrichment orchestration: HubSpot object -> Forager -> HubSpot update."""
import logging
from dataclasses import dataclass, field

from .config import Settings
from .forager_client import ForagerClient
from .hubspot_client import HubSpotClient

log = logging.getLogger("enricher")


@dataclass
class EnrichmentResult:
    ok: bool = True
    notes: list[str] = field(default_factory=list)


def _first(*values):
    for v in values:
        if v:
            return v
    return None


def _split_location(location: dict | None, osm: dict | None) -> tuple[str | None, str | None, str | None]:
    """Extract (city, state, country) from Forager location objects."""
    if not location and not osm:
        return None, None, None
    src = osm or location or {}
    city = _first(src.get("city"), (location or {}).get("name"))
    state = _first(src.get("state"), src.get("region"))
    country = _first(src.get("country"), src.get("country_code"), (location or {}).get("country"))
    return city, state, country


def _public_id(linkedin_info: dict | None) -> str | None:
    if not linkedin_info:
        return None
    return linkedin_info.get("public_identifier")


def _linkedin_url(linkedin_info: dict | None) -> str | None:
    if not linkedin_info:
        return None
    return _first(
        linkedin_info.get("public_profile_url"),
        (f"https://www.linkedin.com/in/{linkedin_info['public_identifier']}"
         if linkedin_info.get("public_identifier") else None),
    )


class Enricher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.forager = ForagerClient(settings)
        self.hubspot = HubSpotClient(settings)

    async def aclose(self):
        await self.forager.aclose()
        await self.hubspot.aclose()

    # ------------------------------------------------------------- company
    async def enrich_company_by_id(self, company_id: str) -> EnrichmentResult:
        result = EnrichmentResult()
        company = await self.hubspot.get_company(company_id)
        if not company:
            result.ok = False
            result.notes.append("company not found in HubSpot")
            return result
        props = company.get("properties", {})
        domain = _first(props.get("domain"), props.get("website"))
        name = props.get("name")
        if not domain and not name:
            result.ok = False
            result.notes.append("company has no domain/name to enrich with")
            return result

        org = await self.forager.enrich_company(domain or name)  # type: ignore[arg-type]
        if not org:
            result.ok = False
            result.notes.append("Forager returned no company data")
            return result

        update: dict = {}
        if org.get("description"):
            update["description"] = org["description"]
        for src, dst in (
            ("annual_revenue", "annualrevenue"),
            ("revenue", "annualrevenue"),
            ("employees", "numberofemployees"),
            ("employee_count", "numberofemployees"),
            ("industry", "industry"),
            ("website", "website"),
            ("domain", "domain"),
        ):
            if org.get(src) and not props.get(dst):
                update[dst] = org[src]
        li = org.get("linkedin") or org.get("linkedin_info") or {}
        if li.get("public_profile_url"):
            update["linkedin_company_page"] = li["public_profile_url"]
        elif li.get("public_identifier"):
            update["linkedin_company_page"] = f"https://www.linkedin.com/company/{li['public_identifier']}"

        if update:
            ok = await self.hubspot.update_company(company_id, update)
            result.notes.append(f"company updated: {sorted(update)} (ok={ok})")
        else:
            result.notes.append("company: nothing new to write")
        result.notes.append(f"company raw keys: {sorted(org)[:25]}")  # extra-details discussion material
        return result

    # ------------------------------------------------------------- contacts
    async def _enrich_person_into_props(
        self, person: dict, role: dict | None
    ) -> tuple[dict, EnrichmentResult]:
        """person: Forager person object. Returns (hubspot_properties, result)."""
        result = EnrichmentResult()
        li_info = person.get("linkedin_info") or {}
        public_id = _public_id(li_info)

        props: dict = {}
        props["firstname"] = _first(person.get("first_name"), (person.get("full_name") or "").split(" ")[0])
        props["lastname"] = _first(
            person.get("last_name"), " ".join((person.get("full_name") or "").split(" ")[1:])
        )
        headline = person.get("headline")
        props["jobtitle"] = _first((role or {}).get("title"), headline)
        if headline:
            props["person_headline"] = headline
        if person.get("description"):
            props["person_description"] = person["description"][:4000]
        if person.get("full_name"):
            props["company"] = (role or {}).get("organization_name") or props.get("company")

        url = _linkedin_url(li_info)
        if url:
            props["linkedin_url"] = url

        osm = (person.get("location") or {}).get("osm_locations") or [{}]
        city, state, country = _split_location(person.get("location"), osm[0] if osm else None)
        if city:
            props["city"] = city
        if state:
            props["state"] = state
        if country:
            props["country"] = country

        # credit-hungry lookups (optional per task spec)
        if public_id and self.settings.fetch_work_email:
            email = await self.forager.work_email(public_id)
            if email:
                props["email"] = email
            else:
                result.notes.append("work email: not available")
        if public_id and self.settings.fetch_phone:
            phone = await self.forager.phone_number(public_id)
            if phone:
                props["phone"] = phone
            else:
                result.notes.append("phone: not available")
        return props, result

    async def enrich_contact_by_id(self, contact_id: str) -> EnrichmentResult:
        result = EnrichmentResult()
        contact = await self.hubspot.get_contact(contact_id)
        if not contact:
            result.ok = False
            result.notes.append("contact not found in HubSpot")
            return result
        props = contact.get("properties", {})
        li_url = props.get("linkedin_url") or ""
        public_id = li_url.rstrip("/").split("/in/")[-1] if "/in/" in li_url else None

        person = None
        if public_id:
            person = await self.forager.person_detail(public_id)
        if not person and props.get("email"):
            data = await self.forager._post(
                "/datastorage/person_detail_reverse_lookup_by_email/",
                {"email": props["email"]},
            )
            person = (data or {}).get("person")
        if not person:
            result.ok = False
            result.notes.append("could not resolve contact in Forager (no linkedin_url / email)")
            return result

        update, sub = await self._enrich_person_into_props(person, None)
        update.pop("email", None)  # never overwrite an existing email with a guess
        if update:
            ok = await self.hubspot.update_contact(contact_id, update)
            result.notes.append(f"contact updated: {sorted(update)} (ok={ok})")
        result.notes.extend(sub.notes)
        return result

    async def find_and_create_contacts(
        self, company_id: str, domain: str
    ) -> EnrichmentResult:
        """Find new people at a company (job-title filter) and create them in HubSpot."""
        result = EnrichmentResult()
        keywords = self.settings.job_title_keywords
        titles = keywords or [None]  # None = unfiltered search
        found = 0

        for title in titles:
            if found >= self.settings.max_contacts_per_company:
                break
            results = await self.forager.find_people_at_company(
                domain, job_title=title, page=0
            )
            for item in results:
                if found >= self.settings.max_contacts_per_company:
                    break
                person = item.get("person") or {}
                role = next(
                    (r for r in person.get("roles", []) if r.get("is_current")),
                    (person.get("roles") or [{}])[0] if person.get("roles") else None,
                )
                li_info = person.get("linkedin_info") or {}
                public_id = _public_id(li_info)
                if not public_id:
                    continue

                # dedupe: already in HubSpot?
                existing = await self.hubspot.find_contact_by_property("linkedin_url", _linkedin_url(li_info))
                if existing:
                    log.info("skipping %s — already in HubSpot", person.get("full_name"))
                    continue

                props, sub = await self._enrich_person_into_props(person, role)
                props["company"] = props.get("company")  # employer name
                props["company_domain"] = domain
                if li_info.get("organization_linkedin_url"):
                    props["company_linkedin_url"] = li_info["organization_linkedin_url"]

                new_id = await self.hubspot.create_contact(props, company_id=company_id)
                if new_id:
                    found += 1
                    result.notes.append(f"created contact {person.get('full_name')} (id={new_id})")
                else:
                    result.notes.append(f"failed to create {person.get('full_name')}")
                result.notes.extend(sub.notes)

        result.notes.append(f"total new contacts created: {found}")
        return result
