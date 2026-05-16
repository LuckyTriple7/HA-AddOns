FROM node:20-alpine

RUN apk add --no-cache jq

WORKDIR /ui

COPY package.json ./
RUN npm install --omit=dev

COPY server.js ./

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
