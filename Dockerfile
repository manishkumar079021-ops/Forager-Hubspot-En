FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN echo 'from fastapi import FastAPI, Request' > main.py && \
    echo 'from config import get_settings' >> main.py && \
    echo 'from enricher import Enricher' >> main.py && \
    echo 'app = FastAPI()' >> main.py && \
    echo '@app.get("/")' >> main.py && \
    echo 'async def root(): return {"status": "online"}' >> main.py && \
    echo '@app.post("/webhook/hubspot")' >> main.py && \
    echo 'async def hubspot_webhook(request: Request):' >> main.py && \
    echo '    settings = get_settings()' >> main.py && \
    echo '    enricher = Enricher(settings)' >> main.py && \
    echo '    await enricher.aclose()' >> main.py && \
    echo '    return {"status": "success"}' >> main.py
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
