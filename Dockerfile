FROM python:3.11-slim

RUN apt-get update && \
    apt-get -y --no-install-recommends install curl libcap2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

HEALTHCHECK --interval=2m --timeout=5s CMD curl -f http://localhost:10137/health || exit 1

# rest port
EXPOSE 10137/tcp

WORKDIR /app
CMD ["ts-gw2-verify-bot"]

COPY . .
RUN pip install --no-cache-dir .

#VOLUME /app/data
#VOLUME /app/config
#VOLUME /app/logs
