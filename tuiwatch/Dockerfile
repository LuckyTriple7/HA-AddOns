FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="TUIWatch"
LABEL org.opencontainers.image.description="TUI Reisepreis-Tracker für Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    CHROMIUM_PATH=/usr/bin/chromium

# Chromium + Python + Schriften (für korrektes Rendering der Preise)
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        python3 \
        python3-pip \
        curl \
        ca-certificates \
        fonts-liberation \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Playwright nutzt das System-Chromium (CHROMIUM_PATH) → kein 'playwright install' nötig
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY app.py scraper.py tripparser.py aktionscodes.py nextcloud.py packliste.py ./
COPY trips_routes.py backup_routes.py digest.py ai_client.py price_calendar.py watch.py ai_routes.py offers_routes.py ./
COPY check24_client.py check24_routes.py email_search.py market_basket.py stats_routes.py share_routes.py ./
COPY str_flights_client.py str_flights_routes.py trippilot_questions.py ./
COPY fra_flights_client.py fra_flights_routes.py fra_board_client.py ./
COPY muc_flights_client.py muc_flights_routes.py ./
COPY all_flights_routes.py ./
# Auslieferungsstand des TripPilot-Fragebogens — muss neben trippilot_questions.py
# liegen und wird beim Start nach /config/trippilot kopiert (dort editierbar)
COPY trippilot_questions.json ./
COPY icon-192.png icon-512.png ./
COPY templates/ templates/
COPY static/ static/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17794 17796

HEALTHCHECK --interval=30s --timeout=10s --start-period=25s --retries=3 \
    CMD curl -sf http://localhost:17794/health || exit 1

CMD ["/run.sh"]
