import logging
from fastapi import FastAPI, Request
from config import get_settings
from enricher import Enricher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("main")

app = FastAPI(title="Forager HubSpot")

@app.get("/")
async def root():
    return {"status": "online"}

@app.post("/webhook/hubspot")
async def hubspot_webhook(request: Request):
    try:
        body = await request.json()
        log.info(f"Webhook received: {body}")
        settings = get_settings()
        enricher = Enricher(settings)
        await enricher.aclose()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}