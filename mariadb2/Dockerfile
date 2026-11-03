FROM alpine:3.24

RUN apk add --no-cache \
    bash=5.3.9-r1 \
    jq=1.8.2-r0 \
    mariadb=11.8.9-r0 \
    mariadb-client=11.8.9-r0 \
    mariadb-server-utils=11.8.9-r0 \
    pwgen=2.08-r3

# Remove default Alpine MariaDB config (may contain skip-networking)
RUN rm -f /etc/my.cnf /etc/mysql/my.cnf && \
    rm -rf /etc/my.cnf.d /etc/mysql/conf.d

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
