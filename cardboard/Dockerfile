FROM python:3.15-alpine3.24

RUN apk add --no-cache \
    jq=1.8.2-r0 \
    curl=8.23.0-r0

COPY rootfs/app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY rootfs/ /
COPY icon.png /app/static/favicon.png
RUN chmod +x /run.sh

EXPOSE 17772
CMD ["/run.sh"]
