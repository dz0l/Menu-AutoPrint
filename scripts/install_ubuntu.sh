#!/usr/bin/env bash
printf '%s\n' '[menu-autoprint] Installation script started.' >&2

set -euo pipefail

_MENU_INSTALL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_MENU_INSTALL_LIB="${_MENU_INSTALL_SCRIPT_DIR}/install/lib.sh"

if [[ ! -f "${_MENU_INSTALL_LIB}" ]]; then
  # curl|bash: companion lib is not beside this script — fetch from the same raw tree.
  _MENU_INSTALL_LIB_URL="${MENU_AUTOPRINT_INSTALL_LIB_URL:-}"
  if [[ -z "${_MENU_INSTALL_LIB_URL}" ]]; then
    if [[ -n "${REPO_URL:-}" ]]; then
      _MENU_INSTALL_REPO_PATH="$(printf '%s' "${REPO_URL}" | sed -E 's#^https?://github.com/##; s#\.git$##; s#/$##')"
      _MENU_INSTALL_LIB_URL="https://raw.githubusercontent.com/${_MENU_INSTALL_REPO_PATH}/main/scripts/install/lib.sh"
    else
      _MENU_INSTALL_LIB_URL="https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install/lib.sh"
    fi
  fi
  _MENU_INSTALL_TMP="$(mktemp -d)"
  _MENU_INSTALL_LIB="${_MENU_INSTALL_TMP}/lib.sh"
  if ! curl -fsSL "${_MENU_INSTALL_LIB_URL}" -o "${_MENU_INSTALL_LIB}"; then
    echo "Failed to download install helpers from ${_MENU_INSTALL_LIB_URL}" >&2
    echo "Set MENU_AUTOPRINT_INSTALL_LIB_URL or run from a cloned repo: bash scripts/install_ubuntu.sh" >&2
    exit 1
  fi
fi

# shellcheck source=install/lib.sh
source "${_MENU_INSTALL_LIB}"

if [[ -z "$REPO_URL" ]]; then
  echo "Set REPO_URL, for example:"
  echo ""
  echo "  curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | \\"
  echo "    REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash"
  echo ""
  echo "Default APP_DIR is /opt/menu-autoprint. For WSL tests use APP_DIR=\$HOME/menu-autoprint."
  echo "Do not run from /mnt/c/WINDOWS/system32."
  exit 1
fi

validate_app_dir

log "Menu AutoPrint installation"
log "Target directory: $APP_DIR"
log "Repository: $REPO_URL"
if [[ "$VERBOSE" == "1" ]]; then
  log "VERBOSE=1: command tracing enabled (set -x)"
  set -x
fi
if [[ ! -r /dev/tty ]] && ! sudo -n true 2>/dev/null; then
  log "Hint: when piping into bash, sudo prompts may be hard to see."
  log "Prefer: curl ... -o install.sh && REPO_URL=... bash install.sh"
fi
log "When sudo asks for a password, enter it; long steps may run several minutes with little output."

preflight

trap 'on_err $LINENO' ERR
trap print_install_summary EXIT

HOST_IP="${HOST_IP:-}"
if [[ -z "$HOST_IP" ]]; then
  log "Detecting server IP for ALLOWED_HOSTS..."
  HOST_IP="$(detect_host_ip || true)"
fi
[[ -n "${HOST_IP:-}" ]] && log "Server IP (for ALLOWED_HOSTS): $HOST_IP"

check_network

step "Updating package lists (apt-get update)..."
if ! run_apt_get update; then
  record_error "apt-get update failed. Check network and package sources."
  exit 1
fi
log "apt-get update finished."

step "Installing git, curl, openssl..."
if ! run_apt_get install -y git ca-certificates curl openssl; then
  record_error "Failed to install base packages (git, curl, openssl)."
  exit 1
fi
log "Base packages installed."

step "Installing or verifying Docker..."
if ! command -v docker >/dev/null 2>&1; then
  log "Downloading and running get.docker.com (usually 2-5 minutes)..."
  if [[ "$VERBOSE" == "1" ]]; then
    docker_install_ok=0
    curl -fsSL https://get.docker.com | sudo sh || docker_install_ok=$?
  else
    docker_install_ok=0
    curl -fsSL https://get.docker.com | sudo sh >/dev/null || docker_install_ok=$?
  fi
  if [[ "$docker_install_ok" -ne 0 ]]; then
    record_error "Docker installation script from get.docker.com failed."
    record_note "Check access to https://get.docker.com and retry."
    exit 1
  fi
  log "Docker installed."
else
  log "Docker is already installed; skipping installation."
fi

step "Checking Docker access..."
ensure_docker_access || true

if [[ -d "$APP_DIR/.git" ]]; then
  log "Directory $APP_DIR already exists; skipping git clone."
else
  step "Cloning repository into $APP_DIR..."
  sudo mkdir -p "$APP_DIR"
  sudo chown "$USER":"$USER" "$APP_DIR"
  if [[ -n "$(ls -A "$APP_DIR" 2>/dev/null || true)" ]]; then
    record_error "Directory $APP_DIR exists, is not empty, and is not a git checkout."
    record_note "Remove it (or use uninstall), or set APP_DIR to another path, then re-run the installer."
    exit 1
  fi
  git_clone_args=()
  if [[ "$VERBOSE" != "1" ]]; then
    git_clone_args=(-q)
  fi
  if ! git clone "${git_clone_args[@]}" "$REPO_URL" "$APP_DIR"; then
    record_error "git clone failed for $REPO_URL"
    record_note "Verify REPO_URL, GitHub availability, and disk space."
    exit 1
  fi
  log "Repository cloned."
fi

cd "$APP_DIR"

mkdir -p path

step "Updating code (git pull)..."
if ! git pull --ff-only; then
  record_error "git pull --ff-only failed in $APP_DIR"
  record_note "Resolve git conflicts manually or re-clone into a clean directory."
  exit 1
fi
log "Code updated."

step "Configuring .env..."
if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    record_error ".env.example is missing in the repository."
    exit 1
  fi
  cp .env.example .env
  ENV_CREATED=1
  log "Created .env from .env.example."
else
  log ".env already exists."
fi

prompt_new_install_admin_credentials

# Secrets: never leave xtrace on while reading or assigning them.
set +x
DJANGO_SECRET_KEY_VALUE="$(get_env_value "DJANGO_SECRET_KEY")"
if [[ "$ENV_CREATED" == "1" || -z "$DJANGO_SECRET_KEY_VALUE" || "$DJANGO_SECRET_KEY_VALUE" == "change-me" || "$DJANGO_SECRET_KEY_VALUE" == "changeme" || "$DJANGO_SECRET_KEY_VALUE" == "dev-insecure-change-me" ]]; then
  set_env_value "DJANGO_SECRET_KEY" "$(generate_secret 32)"
fi
unset DJANGO_SECRET_KEY_VALUE

POSTGRES_PASSWORD_VALUE="$(get_env_value "POSTGRES_PASSWORD")"
if [[ "$ENV_CREATED" == "1" || -z "$POSTGRES_PASSWORD_VALUE" || "$POSTGRES_PASSWORD_VALUE" == "change-me" ]]; then
  set_env_value "POSTGRES_PASSWORD" "$(generate_secret 24)"
fi
unset POSTGRES_PASSWORD_VALUE
if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
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

step "Building images and starting containers (docker compose up --build)..."
log "This is the longest step: the first build may take 5-15 minutes."
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
compose_up_quiet_args
if ! compose_cmd "${COMPOSE_UP_ARGS[@]}" up -d --build --remove-orphans "${COMPOSE_UP_EXTRA[@]}"; then
  record_error "docker compose up failed."
  record_note "Run manually: cd $APP_DIR && docker compose up -d --build --remove-orphans"
  record_note "For full Docker output: VERBOSE=1 bash install.sh"
  exit 1
fi
log "Containers started."

step "Running database migrations..."
wait_for_web || exit 1
# Verbosity 1 shows one line per migration — useful progress, not Docker layer spam.
if ! compose_python manage.py migrate --verbosity 1; then
  record_error "Database migrations failed."
  exit 1
fi
log "Migrations finished."

step "Creating admin user..."
set +x
ADMIN_USERNAME="${ADMIN_USERNAME:-${MENU_AUTOPRINT_ADMIN_USERNAME:-mAdmin}}"
if [[ -n "${ADMIN_PASSWORD:-}" ]]; then
  # Credentials were collected earlier for this username — create it even if
  # another admin already exists in a reused Postgres volume.
  if username_exists "$ADMIN_USERNAME"; then
    if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
    log "User '$ADMIN_USERNAME' already exists; skipping creation."
  else
    if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
    log "Creating admin user '$ADMIN_USERNAME'..."
    set +x
    if ! create_admin_user "$ADMIN_USERNAME" "$ADMIN_PASSWORD"; then
      record_error "Admin user creation failed for '$ADMIN_USERNAME'."
      record_note "Run: cd $APP_DIR && docker compose exec -it web python manage.py create_staff_user $ADMIN_USERNAME --role admin"
      unset ADMIN_PASSWORD MENU_AUTOPRINT_NEW_USER_PASSWORD
      exit 1
    fi
    unset ADMIN_PASSWORD MENU_AUTOPRINT_NEW_USER_PASSWORD
    if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
    log "Admin user created: $ADMIN_USERNAME"
  fi
  unset ADMIN_PASSWORD MENU_AUTOPRINT_NEW_USER_PASSWORD
elif admin_exists; then
  if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
  log "An admin user already exists; skipping creation."
else
  if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
  log "No active admin found; password will be requested."
  read_admin_credentials
  log "Creating admin user '$ADMIN_USERNAME'..."
  set +x
  if ! create_admin_user "$ADMIN_USERNAME" "$ADMIN_PASSWORD"; then
    record_error "Admin user creation failed for '$ADMIN_USERNAME'."
    record_note "Run: cd $APP_DIR && docker compose exec -it web python manage.py create_staff_user $ADMIN_USERNAME --role admin"
    unset ADMIN_PASSWORD MENU_AUTOPRINT_NEW_USER_PASSWORD
    exit 1
  fi
  unset ADMIN_PASSWORD MENU_AUTOPRINT_NEW_USER_PASSWORD
  if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
  if ! username_exists "$ADMIN_USERNAME"; then
    record_error "Admin user '$ADMIN_USERNAME' was not created."
    exit 1
  fi
  log "Admin user created: $ADMIN_USERNAME"
fi
if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
step "Clearing cache..."
if ! compose_python manage.py shell -c "from django.core.cache import cache; cache.clear()"; then
  record_warning "Cache clear failed (non-critical)."
fi
log "Installation finished; printing summary..."

if [[ -f fonts/Times\ New\ Roman.ttf && -f fonts/Times\ New\ Roman\ Bold.ttf ]]; then
  echo "Bundled Times New Roman fonts detected in the repository. The web image uses them automatically."
else
  record_warning "Bundled Times New Roman fonts were not found. PDF will use the nearest available serif fallback."
fi

if [[ "$DOCKER_GROUP_ADDED" == "1" ]]; then
  record_note "Docker group was updated. Log out/in before using docker without sudo."
fi
