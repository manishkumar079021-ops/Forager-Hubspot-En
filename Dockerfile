FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Yeh script saari Windows files (UTF-16) ko Linux format (UTF-8) mein convert kar degi
RUN echo "import glob" > fix.py && \
    echo "for f in glob.glob('*.py'):" >> fix.py && \
    echo "    data = open(f, 'rb').read()" >> fix.py && \
    echo "    if b'\x00' in data:" >> fix.py && \
    echo "        text = data.decode('utf-16le', 'ignore')" >> fix.py && \
    echo "        open(f, 'w', encoding='utf-8').write(text)" >> fix.py && \
    python fix.py

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
