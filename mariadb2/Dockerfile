FROM alpine:3.21

RUN apk add --no-cache \
    bash \
    jq \
    mariadb \
    mariadb-client \
    mariadb-server-utils \
    pwgen

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
