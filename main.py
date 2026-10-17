import logging
from fastapi import FastAPI, Request
from .config import get_settings
from .enricher import Enricher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("main")

app = FastAPI(title="Forager HubSpot Enrichment")

@app.get("/")
async def health_check():
    return {"status": "online", "message": "Service is running perfectly!"}

@app.post("/webhook/hubspot")
async def hubspot_webhook(request: Request):
    try:
        body = await request.json()
        log.info("Received HubSpot webhook: %s", body)
        return {"status": "success"}
    except Exception as e:
        log.error("Webhook error: %s", e)
        return {"status": "error", "message": str(e)}
