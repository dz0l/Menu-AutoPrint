#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/menu-autoprint}"
REPO_URL="${REPO_URL:-}"

if [[ -z "$REPO_URL" ]]; then
  echo "Set REPO_URL, for example:"
  echo "curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash"
  exit 1
fi

detect_host_ip() {
  ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i=="src") {print $(i+1); exit}}'
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

append_csv_env_value() {
  local key="$1"
  local value="$2"
  local current=""
  if grep -q "^${key}=" .env; then
    current="$(grep "^${key}=" .env | cut -d= -f2-)"
  fi
  if [[ -z "$current" ]]; then
    set_env_value "$key" "$value"
    return
  fi
  if [[ ",$current," != *",$value,"* ]]; then
    set_env_value "$key" "${current},${value}"
  fi
}

HOST_IP="${HOST_IP:-$(detect_host_ip)}"

sudo apt-get update
sudo apt-get install -y git ca-certificates curl openssl

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

if [[ -z "$(grep '^CADDY_SITE_ADDRESS=' .env | cut -d= -f2- || true)" ]]; then
  set_env_value "CADDY_SITE_ADDRESS" ":80"
fi

if [[ -n "${HOST_IP:-}" ]]; then
  append_csv_env_value "DJANGO_ALLOWED_HOSTS" "$HOST_IP"
  append_csv_env_value "DJANGO_CSRF_TRUSTED_ORIGINS" "http://$HOST_IP"
fi

docker compose up -d --build
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py bootstrap_editor --username mAdmin --password qwerty123
docker compose exec -T web python manage.py shell -c "from django.contrib.auth import get_user_model; user = get_user_model().objects.get(username='mAdmin'); assert user.is_active and user.check_password('qwerty123')"
docker compose exec -T web python manage.py shell -c "from django.core.cache import cache; cache.clear()"

if [[ -f fonts/Times\ New\ Roman.ttf && -f fonts/Times\ New\ Roman\ Bold.ttf ]]; then
  echo "Bundled Times New Roman fonts detected in the repository. The web image uses them automatically."
else
  echo "Bundled Times New Roman fonts were not found in the repository. PDF will use the nearest available serif fallback."
fi

if [[ -n "${HOST_IP:-}" ]]; then
  echo "Menu AutoPrint is running. Open http://$HOST_IP/"
else
  echo "Menu AutoPrint is running. Open the server IP address in your browser."
fi
