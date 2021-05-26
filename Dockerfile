FROM python:3-slim

HEALTHCHECK --interval=2m --timeout=2s CMD curl -f http://localhost:10137/health || exit 1

# rest port
EXPOSE 10137/tcp

WORKDIR /app
CMD ["ts-gw2-verify-bot"]

COPY . .
RUN pip install --no-cache-dir .

#VOLUME /app/data
#VOLUME /app/config
#VOLUME /app/logs
