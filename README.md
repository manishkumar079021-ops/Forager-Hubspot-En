# Forager x HubSpot Enrichment Automation

Custom Python (FastAPI) service that enriches HubSpot companies & contacts
using the Forager API, with live webhook automation and job-title-based
contact discovery. No no-code tools.

## Architecture
- `POST /webhooks/hubspot/company` — company created -> enrich company -> enrich existing contacts -> find & create new contacts (job-title filter)
- `POST /webhooks/hubspot/contact`  — contact created -> enrich contact
- `scripts/demo_openai.py` — builds the demo dataset (OpenAI company + 5 people)

## 1. Setup
1. Forager: create account at app.forager.ai -> API section -> copy API key + account id (150 free credits).
2. HubSpot: developer account -> test portal -> Settings -> Integrations -> Private Apps -> create app with `crm.objects.companies.read/write`, `crm.objects.contacts.read/write` scopes -> copy token.
3. Create custom contact properties in HubSpot (Settings -> Properties -> Contacts): `linkedin_url`, `person_headline`, `person_description`, `company_domain`, `company_linkedin_url` (all single-line text). Company properties used are all defaults.

## 2. Local run
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
uvicorn app.main:app --reload
```

## 3. Deploy (Railway)
1. Push this repo to GitHub.
2. railway.app -> New Project -> Deploy from GitHub repo.
3. Railway auto-detects the Dockerfile. Add the same env vars (copy from .env) in Variables tab.
4. Copy the generated public URL, e.g. `https://xxx.up.railway.app`.

## 4. HubSpot webhooks
Settings -> Integrations -> Webhooks -> create subscription:
- objectType: `company`, event: `created`, target: `https://xxx.up.railway.app/webhooks/hubspot/company?secret=YOUR_SECRET`
- objectType: `contact`, event: `created`, target: `https://xxx.up.railway.app/webhooks/hubspot/contact?secret=YOUR_SECRET`

## 5. Demo
```
python -m scripts.demo_openai
```
Fetches openai.com company + 5 current people matching `JOB_TITLE_FILTER`,
creates them in HubSpot associated to the company, enriches email/phone when available.

## Credit budget (150 free)
company enrich = 1, person search = 1, work email = 5, mobile = 15.
Demo: 1 + 1 + 5*(5 email) = 31 credits (phone optional; 5 phones = +75).
Set FETCH_PHONE=false if credits run low — task spec marks phone "if available".
