# Menu AutoPrint

Django/PostgreSQL version of Menu AutoPrint for building bilingual menus, maintaining the dish database, and generating print-ready PDF files.

Repository: `https://github.com/dz0l/Menu-AutoPrint`

## Ubuntu Installation

```bash
curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash
```

The installer clones or updates the repository, creates `.env` if needed, configures the detected server address, builds Docker services, runs migrations, creates the bootstrap editor account, and collects static files.

Default editor account: `mAdmin` / `qwerty123`

The password must be changed after the first login.
New passwords must include at least 8 characters, one uppercase letter, and one special character.

Default deployment runs through `Caddy` in LAN/HTTP mode with `CADDY_SITE_ADDRESS=:80`.
Only Caddy publishes ports to the host; `nginx` and `web` stay internal to the Docker network.
`CADDY_BIND_ADDRESS=0.0.0.0` exposes Caddy on the server network. Use `127.0.0.1` for local-only access.
For public HTTPS later, update `.env`: set `CADDY_SITE_ADDRESS` to your domain, keep `CADDY_BIND_ADDRESS=0.0.0.0`, enable `DJANGO_ENABLE_HTTPS=1`, and set matching `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.

```bash
.env:
CADDY_SITE_ADDRESS=your-domain.tld
CADDY_BIND_ADDRESS=0.0.0.0
DJANGO_ENABLE_HTTPS=1
DJANGO_ALLOWED_HOSTS=your-domain.tld,...
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.tld
docker compose up -d --build
```

## CSV Import From Server Path

If `calories.csv` was uploaded to the server after the container was started, copy it into the running `web` container first:

```bash
cd /opt/menu-autoprint
WEB_ID="$(docker compose ps -q web)"
docker cp /opt/menu-autoprint/path/calories.csv "${WEB_ID}:/tmp/calories.csv"
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --dry-run
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv
```

```bash
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --apply-updates
```

To fully replace the current dishes table with the CSV contents:

```bash
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --replace-all --dry-run
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --replace-all
```

## Maintenance

```bash
cd /opt/menu-autoprint
git pull
docker compose up -d --build web
```

`web` runs `collectstatic` automatically on container start. Do not run a second manual `collectstatic` immediately after rebuilding `web`.

Create a manual PostgreSQL backup:

```bash
cd /opt/menu-autoprint
docker compose run --rm backup sh /scripts/backup_postgres.sh once
```

Rollback notes are in `ROLLBACK.md`.

Reset the bootstrap editor account if first login does not work:

```bash
cd /opt/menu-autoprint
docker compose exec web python manage.py bootstrap_editor --username mAdmin --password qwerty123
docker compose exec web python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```
