FROM python:3

HEALTHCHECK --interval=2m --timeout=2s CMD curl -f http://localhost:8080/health || exit 1

#for later use
#EXPOSE 8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD [ "python", "./Main.py" ]

#VOLUME /app/data
#VOLUME /app/config
#VOLUME /app/logs