FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      shared-mime-info \
      fonts-dejavu \
      fonts-liberation2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Build has no .env; runtime still requires a real DJANGO_SECRET_KEY when DEBUG=0.
RUN DJANGO_SECRET_KEY=build-only-collectstatic python manage.py collectstatic --noinput

CMD ["sh", "/app/scripts/start_web.sh"]
