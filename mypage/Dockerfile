FROM python:3.14-alpine

LABEL org.opencontainers.image.title="MyPage"
LABEL org.opencontainers.image.description="Homepage builder for Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/LuckyTriple7/HA-AddOns"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache curl cifs-utils jq ttf-dejavu

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY game_66.py .
COPY game_20ab.py .
COPY game_schwimmen.py .
COPY game_maumau.py .
COPY game_praesident.py .
COPY game_jeopardy.py .
COPY game_gluecksrad.py .
COPY game_dice.py .
COPY game_kniffel.py .
COPY game_66_rules_de.md game_66_rules_en.md ./
COPY game_20ab_rules_de.md game_20ab_rules_en.md ./
COPY game_schwimmen_rules_de.md game_schwimmen_rules_en.md ./
COPY game_maumau_rules_de.md game_maumau_rules_en.md ./
COPY game_praesident_rules_de.md game_praesident_rules_en.md ./
COPY game_jeopardy_rules_de.md game_jeopardy_rules_en.md ./
COPY game_gluecksrad_rules_de.md game_gluecksrad_rules_en.md ./
COPY game_kniffel_rules_de.md game_kniffel_rules_en.md ./
COPY data/ data/
COPY icon.png .
COPY fonts/ fonts/
COPY templates/ templates/
COPY locales/ locales/
COPY static/ static/
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 17760 17761

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:17760/health || exit 1

CMD ["/run.sh"]
