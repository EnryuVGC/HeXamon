FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY data ./data
COPY assets ./assets

RUN useradd --create-home --uid 1000 botuser
USER botuser

CMD ["python", "-m", "bot.main"]
