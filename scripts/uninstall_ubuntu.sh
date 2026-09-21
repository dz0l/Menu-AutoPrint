#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/menu-autoprint}"
REMOVE_APP_DIR=0
REMOVE_DOCKER=0
YES=0

usage() {
  cat <<'EOF'
Full removal of Menu AutoPrint.

Usage:
  bash scripts/uninstall_ubuntu.sh [options]

Options:
  --app-dir PATH       Application directory (default: /opt/menu-autoprint)
  --remove-app-dir     Delete application directory and local backups
  --remove-docker      Remove Docker Engine and related packages from the host
  --yes                Do not ask for confirmation
  -h, --help           Show this help

Examples:
  # Stop containers and remove volumes, keep app files and Docker:
  bash scripts/uninstall_ubuntu.sh --yes

  # Also delete /opt/menu-autoprint:
  bash scripts/uninstall_ubuntu.sh --remove-app-dir --yes

  # Full host cleanup including Docker Engine:
  bash scripts/uninstall_ubuntu.sh --remove-app-dir --remove-docker --yes
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir)
      APP_DIR="$2"
      shift 2
      ;;
    --remove-app-dir)
      REMOVE_APP_DIR=1
      shift
      ;;
    --remove-docker)
      REMOVE_DOCKER=1
      shift
      ;;
    --yes|-y)
      YES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

docker_cmd() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
    return
  fi
  if sudo docker info >/dev/null 2>&1; then
    sudo docker "$@"
    return
  fi
  return 1
}

confirm() {
  local prompt="$1"
  if [[ "$YES" == "1" ]]; then
    return 0
  fi
  read -r -p "$prompt [y/N]: " answer
  [[ "$answer" == "y" || "$answer" == "Y" ]]
}

confirm() {
  local prompt="$1"
  if [[ "$YES" == "1" ]]; then
    return 0
  fi
  read -r -p "$prompt [y/N]: " answer
  [[ "$answer" == "y" || "$answer" == "Y" ]]
}

is_menu_autoprint_dir() {
  local dir="$1"
  [[ -f "$dir/docker-compose.yml" ]] || return 1
  [[ -f "$dir/manage.py" ]] || return 1
  [[ -d "$dir/apps/menu" ]] || return 1
  [[ -f "$dir/apps/menu/apps.py" ]] || return 1
  return 0
}

resolve_and_validate_app_dir() {
  local resolved=""
  if [[ ! -d "$APP_DIR" ]]; then
    echo "APP_DIR does not exist: $APP_DIR" >&2
    exit 1
  fi
  if command -v readlink >/dev/null 2>&1; then
    resolved="$(readlink -f "$APP_DIR" 2>/dev/null || true)"
  fi
  if [[ -z "$resolved" ]] && command -v realpath >/dev/null 2>&1; then
    resolved="$(realpath "$APP_DIR" 2>/dev/null || true)"
  fi
  if [[ -z "$resolved" ]]; then
    echo "Unable to resolve APP_DIR to a canonical absolute path: $APP_DIR" >&2
    exit 1
  fi
  if [[ "$resolved" != /* ]]; then
    echo "Refusing non-absolute APP_DIR=$resolved" >&2
    exit 1
  fi
  case "$resolved" in
    /|/home|/opt|/var|/usr|/etc|/root|/mnt|/media|/tmp)
      echo "Refusing unsafe APP_DIR=$resolved" >&2
      exit 1
      ;;
  esac
  if [[ "$resolved" != /opt/* && "$resolved" != /home/* ]]; then
    # Allow only typical install roots unless explicitly under /opt or /home.
    if [[ "$YES" != "1" ]]; then
      echo "Unusual APP_DIR=$resolved (expected under /opt or /home)." >&2
    fi
  fi
  if ! is_menu_autoprint_dir "$resolved"; then
    echo "Refusing $resolved: not a Menu AutoPrint application directory." >&2
    echo "Expected docker-compose.yml, manage.py, and apps/menu." >&2
    exit 1
  fi
  APP_DIR="$resolved"
}

resolve_and_validate_app_dir

echo "Menu AutoPrint uninstall"
echo "App directory: $APP_DIR"
echo "Remove app directory: $([[ "$REMOVE_APP_DIR" == "1" ]] && echo yes || echo no)"
echo "Remove Docker Engine: $([[ "$REMOVE_DOCKER" == "1" ]] && echo yes || echo no)"
echo ""

if ! confirm "Continue?"; then
  echo "Cancelled."
  exit 0
fi

echo "Stopping Menu AutoPrint containers and removing volumes..."
(
  cd "$APP_DIR"
  docker_cmd compose --profile caddy --profile external-proxy down -v --remove-orphans --rmi local || true
)
project_name="$(basename "$APP_DIR")"
project_name="${project_name//[^a-zA-Z0-9]/_}"
project_name="$(echo "$project_name" | tr '[:upper:]' '[:lower:]')"

if [[ -n "$project_name" ]]; then
  echo "Removing leftover Menu AutoPrint containers (if any)..."
  mapfile -t project_containers < <(docker_cmd ps -aq --filter "label=com.docker.compose.project=${project_name}" 2>/dev/null || true)
  if [[ ${#project_containers[@]} -gt 0 ]]; then
    docker_cmd rm -f "${project_containers[@]}" || true
  fi

  echo "Removing named volumes (if they still exist)..."
  mapfile -t project_volumes < <(docker_cmd volume ls -q --filter "label=com.docker.compose.project=${project_name}" 2>/dev/null || true)
  if [[ ${#project_volumes[@]} -gt 0 ]]; then
    docker_cmd volume rm -f "${project_volumes[@]}" >/dev/null 2>&1 || true
  fi
fi

if [[ "$REMOVE_APP_DIR" == "1" ]]; then
  if [[ -d "$APP_DIR" ]]; then
    if ! is_menu_autoprint_dir "$APP_DIR"; then
      echo "Refusing to delete $APP_DIR: not a Menu AutoPrint app dir." >&2
      exit 1
    fi
    echo "Deleting $APP_DIR ..."
    sudo rm -rf --one-file-system "$APP_DIR"
  fi
fi

if [[ "$REMOVE_DOCKER" == "1" ]]; then
  if ! confirm "Remove Docker Engine, images, and /var/lib/docker from this host?"; then
    echo "Docker removal skipped."
  else
    echo "Stopping Docker service..."
    sudo systemctl stop docker docker.socket containerd >/dev/null 2>&1 || true

    if command -v apt-get >/dev/null 2>&1; then
      echo "Purging Docker packages..."
      sudo apt-get purge -y \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras \
        docker.io docker-doc docker-compose podman-docker containerd runc >/dev/null 2>&1 || true
      sudo apt-get autoremove -y >/dev/null 2>&1 || true
    fi

    echo "Removing Docker data directories..."
    sudo rm -rf /var/lib/docker /var/lib/containerd

    if getent group docker >/dev/null 2>&1; then
      sudo groupdel docker >/dev/null 2>&1 || true
    fi

    echo "Docker removed."
  fi
fi

echo ""
echo "Uninstall finished."
echo "Removed: containers, project volumes, local images for this project."
if [[ "$REMOVE_APP_DIR" == "1" ]]; then
  echo "Removed: application directory $APP_DIR"
fi
if [[ "$REMOVE_DOCKER" == "1" ]]; then
  echo "Removed: Docker Engine (if packages were present)"
fi
