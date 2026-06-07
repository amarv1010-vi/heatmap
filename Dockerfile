FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

# Long timeout: a full watchlist hunt with web search can take a couple minutes.
CMD ["sh", "-c", "gunicorn app:app --workers 2 --threads 4 --timeout 180 --bind 0.0.0.0:${PORT}"]
