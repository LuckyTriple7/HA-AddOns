FROM bbernhard/signal-cli-rest-api:latest

# Seit 0.101 laeuft das Basis-Image als signal-api (USER) mit s6-overlay (/init).
# Fuer apt und run.sh wieder root; run.sh startet die API selbst per setpriv als 1000.
USER root

# Install Node.js for the chat UI
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm curl jq && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /ui
COPY package.json .
RUN npm install --production
COPY server.js .

COPY run.sh /run.sh
RUN chmod +x /run.sh

ENTRYPOINT ["/run.sh"]
