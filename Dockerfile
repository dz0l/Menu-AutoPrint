FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      libcairo2 \
      libffi8 \
      libharfbuzz0b \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      shared-mime-info \
      fonts-dejavu \
      fonts-noto \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN python manage.py collectstatic --noinput

CMD ["sh", "/app/scripts/start_web.sh"]
