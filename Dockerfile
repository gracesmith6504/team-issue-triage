FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY profiles/ profiles/

USER 1001

EXPOSE 8080

ENTRYPOINT ["python", "-m", "app"]
