# Shared helpers for Menu AutoPrint Ubuntu installer.
# Sourced by scripts/install_ubuntu.sh — do not execute directly.

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

validate_app_dir() {
  if [[ "$APP_DIR" == /mnt/* ]]; then
    record_error "APP_DIR must not be on a Windows mount ($APP_DIR). Use /opt/menu-autoprint or \$HOME/menu-autoprint."
    exit 1
  fi
}

validate_admin_password() {
  local password="$1"
  local message=""

  if [[ ${#password} -lt 8 ]]; then
    message="Password must be at least 8 characters."
  elif ! [[ "$password" =~ [A-Z] ]]; then
    message="Password must contain at least one uppercase letter."
  elif ! [[ "$password" =~ [^A-Za-z0-9] ]]; then
    message="Password must contain at least one special character."
  fi

  if [[ -n "$message" ]]; then
    echo "$message"
    return 1
  fi
  return 0
}

preflight() {
  log "Working directory: $PWD"
  case "$PWD" in
    /mnt/c/WINDOWS/system32* | /mnt/c/Windows/System32*)
      log "ERROR: do not run the installer from system32."
      log "curl often cannot save install.sh there, and bash may report: No such file or directory."
      log "Run: cd ~   then download and run the installer again."
      exit 1
      ;;
  esac
  if [[ "$PWD" == /mnt/c/* ]]; then
    record_warning "Running from /mnt/c/... is slower; for WSL use: cd ~"
  fi
}

check_network() {
  log "Checking GitHub access (up to 15 s)..."
  if command -v timeout >/dev/null 2>&1; then
    if timeout 15 curl -fsSL -o /dev/null https://github.com; then
      log "GitHub is reachable."
      return 0
    fi
  elif curl -fsSL -o /dev/null https://github.com; then
    log "GitHub is reachable."
    return 0
  fi
  record_error "Cannot reach https://github.com (timeout or DNS failure)."
  record_note "After changing .wslconfig run in PowerShell: wsl --shutdown"
  record_note "Check: curl -v https://github.com"
  record_note "If dnsTunneling=true causes issues, try disabling it temporarily in .wslconfig."
  exit 1
}

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
    echo "  - Password rules: at least 8 characters, 1 uppercase letter, 1 special character."
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

detect_host_ip() {
  local route_output=""
  if command -v timeout >/dev/null 2>&1; then
    route_output="$(timeout 5 ip route get 1.1.1.1 2>/dev/null || true)"
  else
    route_output="$(ip route get 1.1.1.1 2>/dev/null || true)"
  fi
  if [[ -z "$route_output" ]]; then
    record_warning "Could not detect host IP (ip route get 1.1.1.1). Set ALLOWED_HOSTS manually in .env."
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

# All `compose exec` must ignore caller stdin. When install is started as
# `curl ... | bash`, an attached stdin would consume the rest of the script
# and bash would exit "successfully" before migrate/admin steps.
compose_exec() {
  compose_cmd exec -T "$@" </dev/null
}

run_apt_get() {
  if [[ "$VERBOSE" == "1" ]]; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get "$@"
  else
    sudo DEBIAN_FRONTEND=noninteractive apt-get -qq "$@"
  fi
}

compose_up_quiet_args() {
  if [[ "$VERBOSE" == "1" ]]; then
    export BUILDKIT_PROGRESS=plain
    COMPOSE_UP_ARGS=(--progress plain)
    COMPOSE_UP_EXTRA=()
  else
    export BUILDKIT_PROGRESS=quiet
    COMPOSE_UP_ARGS=(--progress quiet)
    COMPOSE_UP_EXTRA=(--quiet-pull --quiet-build)
  fi
}

compose_python() {
  compose_exec web python "$@"
}

wait_for_web() {
  local attempt
  log "Waiting for the web container to accept commands..."
  for attempt in $(seq 1 60); do
    if compose_python -c "import django" >/dev/null 2>&1; then
      log "Web container is ready."
      return 0
    fi
    sleep 2
  done
  record_error "Web container did not become ready in time."
  return 1
}

_shell_bool() {
  local code="$1"
  local result
  result="$(compose_python manage.py shell -c "$code" 2>/dev/null | tr -d '\r' | tail -n 1 | tr -d '[:space:]')"
  [[ "$result" == "1" ]]
}

admin_exists() {
  _shell_bool "from django.contrib.auth import get_user_model; User = get_user_model(); print('1' if User.objects.filter(role='admin', is_active=True).exists() else '0')"
}

username_exists() {
  local username="$1"
  local result
  if docker info >/dev/null 2>&1; then
    result="$(
      env MENU_AUTOPRINT_CHECK_USERNAME="$username" \
        docker compose exec -T -e MENU_AUTOPRINT_CHECK_USERNAME \
        web python manage.py shell -c "import os; from django.contrib.auth import get_user_model; User = get_user_model(); print('1' if User.objects.filter(username=os.environ['MENU_AUTOPRINT_CHECK_USERNAME']).exists() else '0')" \
        </dev/null 2>/dev/null | tr -d '\r' | tail -n 1 | tr -d '[:space:]'
    )"
  else
    result="$(
      sudo env MENU_AUTOPRINT_CHECK_USERNAME="$username" \
        docker compose exec -T -e MENU_AUTOPRINT_CHECK_USERNAME \
        web python manage.py shell -c "import os; from django.contrib.auth import get_user_model; User = get_user_model(); print('1' if User.objects.filter(username=os.environ['MENU_AUTOPRINT_CHECK_USERNAME']).exists() else '0')" \
        </dev/null 2>/dev/null | tr -d '\r' | tail -n 1 | tr -d '[:space:]'
    )"
  fi
  [[ "$result" == "1" ]]
}

create_admin_user() {
  local username="$1"
  local password="$2"
  set +x
  if [[ -z "$username" || -z "$password" ]]; then
    record_error "Admin username/password missing; cannot create admin user."
    if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
    return 1
  fi
  # Pass password via inherited env so special characters stay intact (incl. sudo path).
  if docker info >/dev/null 2>&1; then
    env MENU_AUTOPRINT_NEW_USER_PASSWORD="$password" \
      docker compose exec -T -e MENU_AUTOPRINT_NEW_USER_PASSWORD \
      web python manage.py create_staff_user "$username" --role admin \
      </dev/null
  else
    sudo env MENU_AUTOPRINT_NEW_USER_PASSWORD="$password" \
      docker compose exec -T -e MENU_AUTOPRINT_NEW_USER_PASSWORD \
      web python manage.py create_staff_user "$username" --role admin \
      </dev/null
  fi
  local status=$?
  if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
  return "$status"
}

read_admin_credentials() {
  set +x
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
      if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
      exit 1
    fi

    local password_repeat password_error
    echo "Password rules: at least 8 characters, 1 uppercase letter, 1 special character." > /dev/tty
    while true; do
      printf 'Admin password (hidden): ' > /dev/tty
      read -r -s ADMIN_PASSWORD < /dev/tty
      printf '\n' > /dev/tty
      printf 'Admin password again: ' > /dev/tty
      read -r -s password_repeat < /dev/tty
      printf '\n' > /dev/tty

      if [[ -z "$ADMIN_PASSWORD" ]]; then
        echo "Password must not be empty." > /dev/tty
      elif [[ "$ADMIN_PASSWORD" != "$password_repeat" ]]; then
        echo "Passwords do not match." > /dev/tty
      elif ! password_error="$(validate_admin_password "$ADMIN_PASSWORD")"; then
        echo "$password_error" > /dev/tty
      else
        break
      fi
    done
  elif ! password_error="$(validate_admin_password "$ADMIN_PASSWORD")"; then
    record_error "$password_error"
    if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
    exit 1
  fi
  if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
}

prompt_new_install_admin_credentials() {
  if [[ "$ENV_CREATED" != "1" ]]; then
    return
  fi
  set +x
  if [[ -n "${MENU_AUTOPRINT_NEW_USER_PASSWORD:-}" ]]; then
    if ! password_error="$(validate_admin_password "$MENU_AUTOPRINT_NEW_USER_PASSWORD")"; then
      record_error "$password_error"
      if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
      exit 1
    fi
    ADMIN_USERNAME="${MENU_AUTOPRINT_ADMIN_USERNAME:-mAdmin}"
    ADMIN_PASSWORD="$MENU_AUTOPRINT_NEW_USER_PASSWORD"
    if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi
    return
  fi
  if [[ "${VERBOSE:-0}" == "1" ]]; then set -x; fi

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
