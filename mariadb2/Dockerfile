FROM alpine:3.21

RUN apk add --no-cache \
    bash \
    jq \
    mariadb \
    mariadb-client \
    mariadb-server-utils \
    pwgen

# Remove default Alpine MariaDB config (may contain skip-networking)
RUN rm -f /etc/my.cnf /etc/mysql/my.cnf && \
    rm -rf /etc/my.cnf.d /etc/mysql/conf.d

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
