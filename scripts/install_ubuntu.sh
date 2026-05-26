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

get_env_value() {
  local key="$1"
  grep "^${key}=" .env 2>/dev/null | cut -d= -f2- || true
}

generate_secret() {
  local bytes="${1:-32}"
  openssl rand -hex "$bytes" 2>/dev/null || date +%s%N
}

append_csv_env_value() {
  local key="$1"
  local value="$2"
  local current=""
  current="$(get_env_value "$key")"
  if [[ -z "$current" ]]; then
    set_env_value "$key" "$value"
    return
  fi
  if [[ ",$current," != *",$value,"* ]]; then
    set_env_value "$key" "${current},${value}"
  fi
}

admin_exists() {
  local result
  result="$(docker compose exec -T web python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print('1' if User.objects.filter(role='admin', is_active=True).exists() else '0')" | tr -d '\r')"
  [[ "$result" == "1" ]]
}

read_admin_credentials() {
  ADMIN_USERNAME="${MENU_AUTOPRINT_ADMIN_USERNAME:-}"
  ADMIN_PASSWORD="${MENU_AUTOPRINT_NEW_USER_PASSWORD:-}"

  if [[ -z "$ADMIN_USERNAME" ]]; then
    ADMIN_USERNAME="mAdmin"
    if [[ -r /dev/tty ]]; then
      local input_username
      printf 'Admin username [%s]: ' "$ADMIN_USERNAME" > /dev/tty
      read -r input_username < /dev/tty
      if [[ -n "$input_username" ]]; then
        ADMIN_USERNAME="$input_username"
      fi
    fi
  fi

  if [[ -z "$ADMIN_PASSWORD" ]]; then
    if [[ ! -r /dev/tty ]]; then
      echo "Set MENU_AUTOPRINT_NEW_USER_PASSWORD for non-interactive admin creation."
      exit 1
    fi

    local password_repeat
    while true; do
      printf 'Admin password (hidden): ' > /dev/tty
      read -r -s ADMIN_PASSWORD < /dev/tty
      printf '\n' > /dev/tty
      printf 'Admin password again: ' > /dev/tty
      read -r -s password_repeat < /dev/tty
      printf '\n' > /dev/tty

      if [[ -z "$ADMIN_PASSWORD" ]]; then
        echo "Password must not be empty."
      elif [[ "$ADMIN_PASSWORD" != "$password_repeat" ]]; then
        echo "Passwords do not match."
      else
        break
      fi
    done
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

ENV_CREATED=0
if [[ ! -f .env ]]; then
  cp .env.example .env
  ENV_CREATED=1
fi

DJANGO_SECRET_KEY_VALUE="$(get_env_value "DJANGO_SECRET_KEY")"
if [[ "$ENV_CREATED" == "1" || -z "$DJANGO_SECRET_KEY_VALUE" ]]; then
  set_env_value "DJANGO_SECRET_KEY" "$(generate_secret 32)"
fi

POSTGRES_PASSWORD_VALUE="$(get_env_value "POSTGRES_PASSWORD")"
if [[ "$ENV_CREATED" == "1" || -z "$POSTGRES_PASSWORD_VALUE" ]]; then
  set_env_value "POSTGRES_PASSWORD" "$(generate_secret 24)"
fi

if [[ -z "$(get_env_value "CADDY_SITE_ADDRESS")" ]]; then
  set_env_value "CADDY_SITE_ADDRESS" ":80"
fi

if [[ -z "$(get_env_value "COMPOSE_PROFILES")" ]]; then
  set_env_value "COMPOSE_PROFILES" "caddy"
fi

if [[ -z "$(get_env_value "CADDY_HTTP_PORT")" ]]; then
  set_env_value "CADDY_HTTP_PORT" "80"
fi

if [[ -z "$(get_env_value "CADDY_HTTPS_PORT")" ]]; then
  set_env_value "CADDY_HTTPS_PORT" "443"
fi

if [[ -z "$(get_env_value "EXTERNAL_PROXY_BIND_ADDRESS")" ]]; then
  set_env_value "EXTERNAL_PROXY_BIND_ADDRESS" "127.0.0.1"
fi

if [[ -z "$(get_env_value "EXTERNAL_PROXY_HTTP_PORT")" ]]; then
  set_env_value "EXTERNAL_PROXY_HTTP_PORT" "8080"
fi

if [[ -n "${HOST_IP:-}" ]]; then
  append_csv_env_value "DJANGO_ALLOWED_HOSTS" "$HOST_IP"
  append_csv_env_value "DJANGO_CSRF_TRUSTED_ORIGINS" "http://$HOST_IP"
fi

docker compose up -d --build
docker compose exec -T web python manage.py migrate
if admin_exists; then
  echo "Admin user already exists; skipping admin creation."
else
  read_admin_credentials
  docker compose exec -T -e MENU_AUTOPRINT_NEW_USER_PASSWORD="$ADMIN_PASSWORD" web python manage.py create_staff_user "$ADMIN_USERNAME" --role admin
  unset ADMIN_PASSWORD
fi
docker compose exec -T web python manage.py shell -c "from django.core.cache import cache; cache.clear()"

if [[ -f fonts/Times\ New\ Roman.ttf && -f fonts/Times\ New\ Roman\ Bold.ttf ]]; then
  echo "Bundled Times New Roman fonts detected in the repository. The web image uses them automatically."
else
  echo "Bundled Times New Roman fonts were not found in the repository. PDF will use the nearest available serif fallback."
fi

COMPOSE_PROFILES_VALUE="$(get_env_value "COMPOSE_PROFILES")"
CADDY_HTTP_PORT_VALUE="$(get_env_value "CADDY_HTTP_PORT")"
EXTERNAL_PROXY_HTTP_PORT_VALUE="$(get_env_value "EXTERNAL_PROXY_HTTP_PORT")"

if [[ "$COMPOSE_PROFILES_VALUE" == *"external-proxy"* ]]; then
  echo "Menu AutoPrint is running behind external proxy on http://127.0.0.1:${EXTERNAL_PROXY_HTTP_PORT_VALUE:-8080}/"
elif [[ -n "${HOST_IP:-}" ]]; then
  if [[ "${CADDY_HTTP_PORT_VALUE:-80}" == "80" ]]; then
    echo "Menu AutoPrint is running. Open http://$HOST_IP/"
  else
    echo "Menu AutoPrint is running. Open http://$HOST_IP:${CADDY_HTTP_PORT_VALUE}/"
  fi
else
  echo "Menu AutoPrint is running. Open the server IP address in your browser."
fi
