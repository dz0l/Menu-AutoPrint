#!/usr/bin/env bash
# Обновляет код сервиса web без скачивания базовых слоёв с Docker Hub.
# Требует уже собранный локальный образ web (например после прошлой полной сборки).
#
# Не устанавливает новые pip/apt-зависимости. Если менялся requirements.txt
# или системные пакеты в Dockerfile — нужен полный:
#   git pull && docker compose up -d --build web


set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

log() {
  printf '[update-web-code] %s\n' "$*" >&2
}

die() {
  printf '[update-web-code] ERROR: %s\n' "$*" >&2
  exit 1
}

if ! command -v docker >/dev/null 2>&1; then
  die "docker не найден"
fi

if [[ ! -f docker-compose.yml ]]; then
  die "нет docker-compose.yml в $ROOT_DIR"
fi

if [[ ! -f Dockerfile.code ]]; then
  die "нет Dockerfile.code в $ROOT_DIR"
fi

compose() {
  docker compose "$@"
}

resolve_base_image() {
  if [[ -n "${MENU_AUTOPRINT_BASE_IMAGE:-}" ]]; then
    printf '%s\n' "$MENU_AUTOPRINT_BASE_IMAGE"
    return
  fi

  local running_id=""
  running_id="$(compose ps -q web 2>/dev/null || true)"
  if [[ -n "$running_id" ]]; then
    local from_running=""
    from_running="$(docker inspect -f '{{.Config.Image}}' "$running_id" 2>/dev/null || true)"
    if [[ -n "$from_running" ]]; then
      printf '%s\n' "$from_running"
      return
    fi
  fi

  local from_images=""
  from_images="$(compose images web --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | head -n 1 || true)"
  if [[ -n "$from_images" && "$from_images" != ":<none>" && "$from_images" != "<none>:<none>" ]]; then
    printf '%s\n' "$from_images"
    return
  fi

  local project=""
  project="$(basename "$ROOT_DIR" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')"
  printf '%s\n' "${project}-web:latest"
}

BASE_IMAGE="$(resolve_base_image)"
log "базовый образ: $BASE_IMAGE"

if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
  # Иногда в Config.Image только имя без тега, а локально есть :latest
  if docker image inspect "${BASE_IMAGE}:latest" >/dev/null 2>&1; then
    BASE_IMAGE="${BASE_IMAGE}:latest"
    log "используем тег: $BASE_IMAGE"
  else
    die "локальный образ «$BASE_IMAGE» не найден. Нужна хотя бы одна успешная полная сборка (docker compose up -d --build web), пока Docker Hub доступен."
  fi
fi

BACKUP_TAG="${BASE_IMAGE%%:*}:pre-code-$(date '+%Y%m%d-%H%M%S')"
log "бэкап тега: $BACKUP_TAG"
docker tag "$BASE_IMAGE" "$BACKUP_TAG"

TARGET_IMAGE="$BASE_IMAGE"
log "сборка Dockerfile.code → $TARGET_IMAGE (без pull)"
docker build \
  --pull=false \
  -f Dockerfile.code \
  --build-arg "BASE_IMAGE=$BASE_IMAGE" \
  -t "$TARGET_IMAGE" \
  .

log "пересоздание контейнера web"
compose up -d --no-build --force-recreate web

log "миграции"
compose exec -T web python manage.py migrate --noinput

log "готово. Откат при необходимости: docker tag $BACKUP_TAG $TARGET_IMAGE && docker compose up -d --no-build --force-recreate web"
log "Штатное обновление (когда Hub доступен): git pull && docker compose up -d --build web"
