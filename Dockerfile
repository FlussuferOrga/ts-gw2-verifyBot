FROM python:3

HEALTHCHECK --interval=2m --timeout=2s CMD curl -f http://localhost:10137/health || exit 1

# rest port
EXPOSE 10137/tcp

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

CMD ["ts-gw2-verify-bot"]

#VOLUME /app/data
#VOLUME /app/config
#VOLUME /app/logs