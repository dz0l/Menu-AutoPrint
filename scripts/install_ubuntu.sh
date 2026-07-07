#!/usr/bin/env bash
printf '%s\n' '[menu-autoprint] Скрипт установки запущен.' >&2

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/menu-autoprint}"
REPO_URL="${REPO_URL:-}"
VERBOSE="${VERBOSE:-0}"
INSTALL_STEP=0
TOTAL_STEPS=11

INSTALL_ERRORS=()
INSTALL_WARNINGS=()
INSTALL_NOTES=()
ENV_CREATED=0
DOCKER_GROUP_ADDED=0

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" >&2
}

step() {
  INSTALL_STEP=$((INSTALL_STEP + 1))
  log "[$INSTALL_STEP/$TOTAL_STEPS] $*"
}

record_error() {
  INSTALL_ERRORS+=("$1")
}

record_warning() {
  INSTALL_WARNINGS+=("$1")
}

record_note() {
  INSTALL_NOTES+=("$1")
}

if [[ -z "$REPO_URL" ]]; then
  echo "Set REPO_URL, for example:"
  echo ""
  echo "  cd ~"
  echo "  curl -fSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh -o install.sh"
  echo "  APP_DIR=\$HOME/menu-autoprint REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash install.sh"
  echo ""
  echo "Do not run from /mnt/c/WINDOWS/system32 — curl may fail to save install.sh there."
  exit 1
fi

preflight() {
  log "Рабочая папка: $PWD"
  case "$PWD" in
    /mnt/c/WINDOWS/system32* | /mnt/c/Windows/System32*)
      log "ОШИБКА: не запускайте установку из system32."
      log "Там curl часто не может сохранить install.sh, а bash выдаёт: No such file or directory."
      log "Выполните: cd ~   и повторите загрузку и запуск."
      exit 1
      ;;
  esac
  if [[ "$PWD" == /mnt/c/* ]]; then
    record_warning "Установка из /mnt/c/... медленнее; для WSL лучше: cd ~"
  fi
}

check_network() {
  log "Проверка доступа к GitHub (до 15 с)..."
  if command -v timeout >/dev/null 2>&1; then
    if timeout 15 curl -fsSL -o /dev/null https://github.com; then
      log "GitHub доступен."
      return 0
    fi
  elif curl -fsSL -o /dev/null https://github.com; then
    log "GitHub доступен."
    return 0
  fi
  record_error "Нет доступа к https://github.com (таймаут или DNS)."
  record_note "После изменения .wslconfig выполните в PowerShell: wsl --shutdown"
  record_note "Проверьте: curl -v https://github.com"
  record_note "При проблемах с dnsTunneling=true попробуйте временно отключить его в .wslconfig."
  exit 1
}

log "Menu AutoPrint — установка"
log "Каталог: $APP_DIR"
log "Репозиторий: $REPO_URL"
if [[ "$VERBOSE" == "1" ]]; then
  log "Режим VERBOSE=1: подробный вывод команд (set -x)"
  set -x
fi
if [[ ! -r /dev/tty ]] && ! sudo -n true 2>/dev/null; then
  log "Подсказка: при pipe в bash запрос sudo может быть неочевиден."
  log "Надёжнее: curl ... -o install.sh && REPO_URL=... bash install.sh"
fi
log "При запросе пароля sudo введите его; apt и сборка Docker могут идти несколько минут без новых строк."

preflight

on_err() {
  record_error "Command failed at line $1 (exit code $?)."
}

print_install_summary() {
  local host_ip="${HOST_IP:-}"
  local profiles http_port

  echo ""
  echo "========== Installation summary =========="

  if [[ ${#INSTALL_ERRORS[@]} -gt 0 ]]; then
    echo "Errors:"
    for item in "${INSTALL_ERRORS[@]}"; do
      echo "  - $item"
    done
    echo ""
    echo "Recommended actions:"
    echo "  - Check internet access to GitHub and get.docker.com."
    echo "  - Re-run the installer after fixing network or DNS issues."
    echo "  - If Docker reports permission denied: log out/in or run: newgrp docker"
    echo "  - Then: cd $APP_DIR && docker compose up -d --build --remove-orphans"
    echo "  - Create admin manually: docker compose exec -it web python manage.py create_staff_user mAdmin --role admin"
  else
    echo "Status: completed without recorded errors."
  fi

  if [[ ${#INSTALL_WARNINGS[@]} -gt 0 ]]; then
    echo ""
    echo "Warnings:"
    for item in "${INSTALL_WARNINGS[@]}"; do
      echo "  - $item"
    done
  fi

  if [[ ${#INSTALL_NOTES[@]} -gt 0 ]]; then
    echo ""
    echo "Notes:"
    for item in "${INSTALL_NOTES[@]}"; do
      echo "  - $item"
    done
  fi

    if [[ -d "$APP_DIR" && -f "$APP_DIR/docker-compose.yml" ]]; then
    profiles="$(grep '^COMPOSE_PROFILES=' "$APP_DIR/.env" | cut -d= -f2- || true)"
    http_port="$(grep '^CADDY_HTTP_PORT=' "$APP_DIR/.env" | cut -d= -f2- || true)"
    echo ""
    if (
      cd "$APP_DIR"
      compose_cmd ps
    ) >/dev/null 2>&1; then
      echo "Containers:"
      (
        cd "$APP_DIR"
        compose_cmd ps
      ) || true
    else
      echo "Containers: could not list (check Docker access: docker ps or newgrp docker)."
    fi

    echo ""
    if [[ "$profiles" == *"external-proxy"* ]]; then
      local proxy_port
      proxy_port="$(grep '^EXTERNAL_PROXY_HTTP_PORT=' "$APP_DIR/.env" | cut -d= -f2- || true)"
      echo "App URL: http://127.0.0.1:${proxy_port:-8080}/"
    elif [[ -n "$host_ip" ]]; then
      if [[ "${http_port:-80}" == "80" ]]; then
        echo "App URL: http://$host_ip/"
      else
        echo "App URL: http://$host_ip:${http_port}/"
      fi
    else
      echo "App URL: open the server IP in your browser."
    fi
  fi

  echo "========================================"
}

trap 'on_err $LINENO' ERR
trap print_install_summary EXIT

detect_host_ip() {
  local route_output=""
  if command -v timeout >/dev/null 2>&1; then
    route_output="$(timeout 5 ip route get 1.1.1.1 2>/dev/null || true)"
  else
    route_output="$(ip route get 1.1.1.1 2>/dev/null || true)"
  fi
  if [[ -z "$route_output" ]]; then
    record_warning "Не удалось определить IP хоста (ip route get 1.1.1.1). ALLOWED_HOSTS можно задать вручную в .env."
    return 0
  fi
  awk '{for (i=1; i<=NF; i++) if ($i=="src") {print $(i+1); exit}}' <<<"$route_output"
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

ensure_docker_access() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
    record_warning "User is in group docker, but access is still denied in this shell."
    record_note "Run: newgrp docker   or log out and back in, then re-run docker compose from $APP_DIR"
    if sudo docker info >/dev/null 2>&1; then
      record_note "This installer will use sudo for Docker commands in the current session."
      return 0
    fi
    record_error "Docker daemon is not reachable."
    return 1
  fi

  if getent group docker >/dev/null 2>&1; then
    sudo usermod -aG docker "$USER"
    DOCKER_GROUP_ADDED=1
    record_note "User $USER was added to group docker."
    record_note "Log out and back in, or run: newgrp docker"
  fi

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if sudo docker info >/dev/null 2>&1; then
    record_note "Using sudo for Docker commands in this session."
    return 0
  fi

  record_error "Docker is installed but not available (permission denied or daemon stopped)."
  return 1
}

docker_cmd() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
    return
  fi
  sudo docker "$@"
}

compose_cmd() {
  docker_cmd compose "$@"
}

admin_exists() {
  local result
  result="$(compose_cmd exec -T web python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print('1' if User.objects.filter(role='admin', is_active=True).exists() else '0')" | tr -d '\r')"
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
      record_error "Set MENU_AUTOPRINT_NEW_USER_PASSWORD for non-interactive admin creation."
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

prompt_new_install_admin_credentials() {
  if [[ "$ENV_CREATED" != "1" ]]; then
    return
  fi
  if [[ -n "${MENU_AUTOPRINT_NEW_USER_PASSWORD:-}" ]]; then
    return
  fi

  echo "First admin account will be created after database migrations."
  read_admin_credentials
}

profile_enabled() {
  local profile="$1"
  local profiles
  profiles="$(get_env_value "COMPOSE_PROFILES")"
  [[ ",$profiles," == *",$profile,"* ]]
}

remove_compose_service_if_present() {
  local profile="$1"
  local service="$2"
  if compose_cmd --profile "$profile" ps -q "$service" >/dev/null 2>&1; then
    compose_cmd --profile "$profile" stop "$service" >/dev/null 2>&1 || true
    compose_cmd --profile "$profile" rm -f "$service" >/dev/null 2>&1 || true
  fi
}

cleanup_inactive_profile_services() {
  if ! profile_enabled "caddy"; then
    remove_compose_service_if_present "caddy" "caddy"
  fi
  if ! profile_enabled "external-proxy"; then
    remove_compose_service_if_present "external-proxy" "nginx-public"
  fi
}

HOST_IP="${HOST_IP:-}"
if [[ -z "$HOST_IP" ]]; then
  log "Определение IP сервера для ALLOWED_HOSTS..."
  HOST_IP="$(detect_host_ip || true)"
fi
[[ -n "${HOST_IP:-}" ]] && log "IP сервера (для ALLOWED_HOSTS): $HOST_IP"

check_network

step "Обновление списка пакетов (apt-get update)..."
if ! sudo apt-get update; then
  record_error "apt-get update failed. Check network and package sources."
  exit 1
fi
log "apt-get update завершён."

step "Установка git, curl, openssl..."
if ! sudo apt-get install -y git ca-certificates curl openssl; then
  record_error "Failed to install base packages (git, curl, openssl)."
  exit 1
fi
log "Базовые пакеты установлены."

step "Установка или проверка Docker..."
if ! command -v docker >/dev/null 2>&1; then
  log "Скачивание и запуск скрипта get.docker.com (обычно 2–5 минут)..."
  if ! curl -fsSL https://get.docker.com | sudo sh; then
    record_error "Docker installation script from get.docker.com failed."
    record_note "Check access to https://get.docker.com and retry."
    exit 1
  fi
  log "Docker установлен."
else
  log "Docker уже установлен, пропуск установки."
fi

step "Проверка доступа к Docker..."
ensure_docker_access || true

if [[ ! -d "$APP_DIR/.git" ]]; then
  step "Клонирование репозитория в $APP_DIR..."
  sudo mkdir -p "$APP_DIR"
  sudo chown "$USER":"$USER" "$APP_DIR"
  if ! git clone "$REPO_URL" "$APP_DIR"; then
    record_error "git clone failed for $REPO_URL"
    record_note "Verify REPO_URL, GitHub availability, and disk space."
    exit 1
  fi
  log "Репозиторий склонирован."
else
  log "Каталог $APP_DIR уже существует, пропуск git clone."
fi

cd "$APP_DIR"

step "Обновление кода (git pull)..."
if ! git pull --ff-only; then
  record_error "git pull --ff-only failed in $APP_DIR"
  record_note "Resolve git conflicts manually or re-clone into a clean directory."
  exit 1
fi
log "Код обновлён."

step "Настройка .env..."
if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    record_error ".env.example is missing in the repository."
    exit 1
  fi
  cp .env.example .env
  ENV_CREATED=1
  log "Создан .env из .env.example."
else
  log "Файл .env уже есть."
fi

prompt_new_install_admin_credentials

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

cleanup_inactive_profile_services

step "Сборка образов и запуск контейнеров (docker compose up --build)..."
log "Это самый долгий этап: первая сборка может занять 5–15 минут."
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
export BUILDKIT_PROGRESS="${BUILDKIT_PROGRESS:-plain}"
export COMPOSE_PROGRESS="${COMPOSE_PROGRESS:-plain}"
if ! compose_cmd up -d --build --remove-orphans; then
  record_error "docker compose up failed."
  record_note "Run manually: cd $APP_DIR && docker compose up -d --build --remove-orphans"
  exit 1
fi
log "Контейнеры запущены."

step "Миграции базы данных..."
if ! compose_cmd exec -T web python manage.py migrate; then
  record_error "Database migrations failed."
  exit 1
fi
log "Миграции выполнены."

step "Создание администратора..."
if admin_exists; then
  log "Администратор уже есть — пропуск создания."
else
  if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
    log "Активного администратора нет — будет запрошен пароль."
    read_admin_credentials
  fi
  if ! compose_cmd exec -T -e MENU_AUTOPRINT_NEW_USER_PASSWORD="$ADMIN_PASSWORD" web python manage.py create_staff_user "$ADMIN_USERNAME" --role admin; then
    record_error "Admin user creation failed."
    record_note "Run: cd $APP_DIR && docker compose exec -it web python manage.py create_staff_user mAdmin --role admin"
    exit 1
  fi
  unset ADMIN_PASSWORD
  if ! admin_exists; then
    record_error "Admin user was not created."
    exit 1
  fi
  log "Администратор создан: $ADMIN_USERNAME"
fi

step "Очистка кэша..."
if ! compose_cmd exec -T web python manage.py shell -c "from django.core.cache import cache; cache.clear()"; then
  record_warning "Cache clear failed (non-critical)."
fi
log "Установка завершена, формируется итоговый отчёт..."

if [[ -f fonts/Times\ New\ Roman.ttf && -f fonts/Times\ New\ Roman\ Bold.ttf ]]; then
  echo "Bundled Times New Roman fonts detected in the repository. The web image uses them automatically."
else
  record_warning "Bundled Times New Roman fonts were not found. PDF will use the nearest available serif fallback."
fi

if [[ "$DOCKER_GROUP_ADDED" == "1" ]]; then
  record_note "Docker group was updated. Log out/in before using docker without sudo."
fi
