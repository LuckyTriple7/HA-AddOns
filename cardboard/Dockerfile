FROM python:3.11-alpine

RUN apk add --no-cache jq

COPY rootfs/app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY rootfs/ /
COPY icon.png /app/static/favicon.png
RUN chmod +x /run.sh

EXPOSE 17772
CMD ["/run.sh"]
