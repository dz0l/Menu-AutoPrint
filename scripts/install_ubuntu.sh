#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/menu-autoprint}"
REPO_URL="${REPO_URL:-}"

if [[ -z "$REPO_URL" ]]; then
  echo "Set REPO_URL, for example: REPO_URL=https://github.com/user/repo.git $0"
  exit 1
fi

sudo apt-get update
sudo apt-get install -y git ca-certificates curl

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
  sudo mkdir -p "$APP_DIR"
  sudo chown "$USER":"$USER" "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git pull --ff-only

if [[ ! -f .env ]]; then
  cp .env.example .env
  SECRET="$(openssl rand -hex 32 2>/dev/null || date +%s%N)"
  sed -i "s/DJANGO_SECRET_KEY=change-me/DJANGO_SECRET_KEY=$SECRET/" .env
fi

docker compose up -d --build
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py bootstrap_editor --username mAdmin --password qwerty123
docker compose exec -T web python manage.py collectstatic --noinput

echo "Menu AutoPrint is running. Open http://$(hostname -I | awk '{print $1}')/"
