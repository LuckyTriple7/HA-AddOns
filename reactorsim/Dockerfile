FROM python:3.14-alpine

LABEL org.opencontainers.image.title="ReactorSim"
LABEL org.opencontainers.image.description="Nuclear power plant control room simulation in the browser"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache curl

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Root-Dateien einzeln, damit dev_run.py und dev_data/ nicht ins Image wandern.
COPY app.py .
COPY auth.py .
COPY persist.py .
COPY scoring.py .
COPY atomic_io.py .
COPY VERSION .

# Verzeichnisse als Ganzes: unter static/js liegen dutzende ES-Module, eine
# Einzelliste liefe garantiert auseinander. Ein vergessenes Modul stürzt nicht
# ab, es liefert still 404 und eine halbtote Oberfläche -- deshalb prüft
# tests/test_dockerfile.py den Importgraph gegen diese COPY-Zeilen.
COPY templates/ templates/
COPY static/ static/
COPY locales/ locales/

COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17779

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17779/health || exit 1

CMD ["/run.sh"]
