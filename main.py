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
