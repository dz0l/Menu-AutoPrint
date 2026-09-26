# Menu AutoPrint

Django/PostgreSQL application for building bilingual menus, maintaining the dish database, and generating print-ready PDF files.

Repository: `https://github.com/dz0l/Menu-AutoPrint`


## Ubuntu Installation

```bash
curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash
```

The installer clones or updates the repository, creates `.env` if needed, generates `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`, configures the detected server address, adds the current user to the `docker` group when needed, builds Docker services, runs migrations, creates the first admin account if none exists, and prints an installation summary with errors and recommendations.



During interactive installation the script asks for the admin username and password.

New passwords must include at least 8 characters, one uppercase letter, and one special character.

For non-interactive installation, pass the first admin credentials through environment variables:

```bash
curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | \
  REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git \
  MENU_AUTOPRINT_ADMIN_USERNAME=mAdmin \
  MENU_AUTOPRINT_NEW_USER_PASSWORD='Strong!Pass123' \
  bash
```



## Full Uninstall

Stop containers, remove project volumes and images:

```bash
cd /opt/menu-autoprint
bash scripts/uninstall_ubuntu.sh --yes
```

Also delete the application directory:

```bash
bash scripts/uninstall_ubuntu.sh --remove-app-dir --yes
```

Remove Docker Engine from the host (destructive; affects all containers on the server):

```bash
bash scripts/uninstall_ubuntu.sh --remove-app-dir --remove-docker --yes
```



## Users

Create an admin:

```bash
cd /opt/menu-autoprint
docker compose exec -it web python manage.py create_staff_user mAdmin --role admin
```

Create a user:

```bash
cd /opt/menu-autoprint
docker compose exec -it web python manage.py create_staff_user editor1 --role user
```

For non-interactive runs:

```bash
cd /opt/menu-autoprint
MENU_AUTOPRINT_NEW_USER_PASSWORD='Strong!Pass123' \
  docker compose exec -T -e MENU_AUTOPRINT_NEW_USER_PASSWORD \
  web python manage.py create_staff_user mAdmin --role admin
```

Reset an existing user's password and role:

```bash
cd /opt/menu-autoprint
docker compose exec -it web python manage.py create_staff_user mAdmin --role admin --update
docker compose exec web python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

Admins are created during installation or via SSH. The web **Users** UI creates only regular users (role `user`); promotion to admin via the GUI is not allowed.

## Network And HTTPS

Default deployment runs through the `caddy` Docker Compose profile in LAN/HTTP mode:

```bash
.env:
COMPOSE_PROFILES=caddy
CADDY_SITE_ADDRESS=:80
CADDY_BIND_ADDRESS=0.0.0.0
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443
DJANGO_ENABLE_HTTPS=0
```

Open the app at `http://server-ip/`.

For public HTTPS managed by Caddy, Caddy must be allowed to bind host ports `80` and `443`:

```bash
.env:
COMPOSE_PROFILES=caddy
CADDY_SITE_ADDRESS=your-domain.tld
CADDY_BIND_ADDRESS=0.0.0.0
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443
DJANGO_ENABLE_HTTPS=1
DJANGO_ALLOWED_HOSTS=your-domain.tld,...
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.tld
```

For external certbot or a host-level reverse proxy, disable Caddy and publish the internal nginx only on a local port. Docker will not occupy host ports `80` or `443`:

```bash
.env:
COMPOSE_PROFILES=external-proxy
EXTERNAL_PROXY_BIND_ADDRESS=127.0.0.1
EXTERNAL_PROXY_HTTP_PORT=8080
DJANGO_ENABLE_HTTPS=1
DJANGO_ALLOWED_HOSTS=your-domain.tld
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.tld
```

Configure the host reverse proxy to send traffic to `http://127.0.0.1:8080/` and pass `X-Forwarded-Proto: https`.  
This mode does not serve public HTTPS by itself; a host-level proxy must listen on `80` and `443`.

If you publish plain HTTP on a non-standard port, open the app as `http://server-ip:port/`.

Archive PDFs and cover images under `media/` are not served directly by nginx: archive downloads and cover previews go through the logged-in application.

```bash
docker compose up -d --build --remove-orphans
```

When switching between `COMPOSE_PROFILES=caddy` and `COMPOSE_PROFILES=external-proxy`, remove the previously active profile service:

```bash
docker compose --profile caddy rm -sf caddy
docker compose --profile external-proxy rm -sf nginx-public
docker compose up -d --build --remove-orphans
```



## CSV Import From Server Path

By default place the CSV on the host under `/opt/menu-autoprint/path/` (for example `/opt/menu-autoprint/path/calories.csv`), then copy it into the running `web` container:

```bash
cd /opt/menu-autoprint
WEB_ID="$(docker compose ps -q web)"
docker cp /opt/menu-autoprint/path/calories.csv "${WEB_ID}:/tmp/calories.csv"
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --dry-run
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv
```

Import can take 1–3 minutes on large files.

```bash
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --apply-updates
```

To fully replace the current dishes table with the CSV contents:

```bash
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --replace-all --dry-run
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --replace-all
```



## Menu PDF Archive

Generated PDFs (normal print mode, not alternate HTML print; admin accounts only) are stored under `media/menu_archive/`.

The same calendar day can keep separate rows per location. Reprinting the same date, location, and menu type as an administrator asks for confirmation in the browser (including on a phone); agreeing overwrites the file, declining leaves the archive unchanged. Alternate HTML print does not write the archive.

Server-managed cover images live under `media/menu_covers/`.

The **Archive** section lists downloads for users and admins. Files older than 730 days are removed automatically;

manually:

```bash
cd /opt/menu-autoprint
docker compose exec web python manage.py purge_menu_archive
```



## Maintenance

```bash
cd /opt/menu-autoprint
git pull
docker compose up -d --build web
```

The `web` container runs `migrate` and `collectstatic` on start (`scripts/start_web.sh`).

Login rate limiting uses Django `FileBasedCache` with a per-key file lock and an explicit TTL window. With multiple workers behind a shared nginx/proxy the limit still shares the cache directory on one host; a shared cache backend (e.g. Redis) is needed for a hard quota across hosts. Behind a reverse proxy, `REMOTE_ADDR` usually identifies the proxy, not the client.

The stock backup saves **PostgreSQL only**. The `media_data` volume (archive PDFs and covers) is **not** included; keep media separately (deferred media backup TODO).

If Docker Hub / CDN stalls while pulling layers but a local `web` image already exists, you can update **application code only** without pulling base images:

```bash
cd /opt/menu-autoprint
git pull
bash scripts/update_web_code.sh
```

The script builds `Dockerfile.code` on top of the current local image, recreates `web`, and runs migrations. It does **not** install new pip/apt packages — if `requirements.txt` or the main `Dockerfile` changed, use a full build once Hub is reachable again.

Create a manual PostgreSQL backup:

```bash
cd /opt/menu-autoprint
docker compose run --rm backup bash /scripts/backup_postgres.sh once
```

Enable auto-translation in the dish editor by setting `AZURE_TRANSLATOR_KEY` in `.env`; for a West Europe Azure Translator resource use `AZURE_TRANSLATOR_REGION=westeurope` and keep `AZURE_TRANSLATOR_ENDPOINT=https://api.cognitive.microsofttranslator.com`. After changing `.env`, recreate the container (`docker compose up -d`); plain `docker compose restart web` does not reload environment.

Host publish of `127.0.0.1:8000` is off by default (use Docker DNS `web:8000`). For a rare host-network peer: `docker compose -f docker-compose.yml -f docker-compose.host-port.example.yml up -d`.

Caddy second site (`CADDY_EXTRA_SITE_ADDRESS` / `CADDY_EXTRA_UPSTREAM`): leave both unset, or set both to real values. An empty `CADDY_EXTRA_SITE_ADDRESS` breaks Caddy startup; the entrypoint unsets empty values.

## Integration API

Narrow server-to-server HTTP API (`/api/integration/v1/`). Disabled by default; does not change normal browser login. Package `apps/integrations/` and shared `apps/menu/document.py` must ship even when `INTEGRATION_API_ENABLED=0`.

1. Create the service account and key:

```bash
docker compose exec web python manage.py create_integration_credential --username integration-service
```

2. Put the printed `INTEGRATION_API_ENABLED=1`, `INTEGRATION_SERVICE_USER_ID`, and `INTEGRATION_API_KEY_HASH` into `.env`. Show the raw key once to the integration client; store only the hash in `.env`.

3. Recreate `web` (`docker compose up -d`) so environment is applied. Call with `Authorization: Bearer <key>`.

`POST /api/integration/v1/menu/archive-status` only reports whether a file with the same date, cover, and menu type already exists (`exists`, `display_name`). It does not write. `POST /api/integration/v1/menu/pdf` still overwrites that file without asking; the client decides whether to check first.

Expired integration operations are purged in batches on new requests (up to 200 per pass); there is no separate cron. Django’s ~20 MB body limit is not a rate limit for heavy PDF work.

Browser cookie sessions cannot use this namespace. The key does not open `/admin/` or the regular browser APIs.

## Optional Telegram bot

A bot with a mini app is not part of this repository’s default `docker compose`. It runs as a separate service on the `menu-autoprint_default` network (service name `menu-telegram`, port `8090` inside Docker only). Day-to-day use is described in [GUIDE.MD](GUIDE.MD), section 12 (Russian).

To run it beside an existing site:

1. Enable the Integration API with the command above. Give the raw key to the bot as `MENU_API_CREDENTIAL`; the site `.env` keeps only the hash.
2. On the bot, set `MENU_API_BASE_URL=http://web:8000/api/integration/v1`, a public `https://` `PUBLIC_MINI_APP_URL`, the bot token, and `SESSION_SECRET`, then `docker compose up -d --build` in the bot directory.
3. If this server’s Caddy should publish the mini app, set both values in the site `.env` and recreate containers (`docker compose up -d`, not `restart`):

```bash
CADDY_EXTRA_SITE_ADDRESS=app.example.com
CADDY_EXTRA_UPSTREAM=menu-telegram:8090
```

4. The user sends `/start` to the bot. Create the first bot administrator:

```bash
docker compose exec menu-telegram python -m backend.cli approve TELEGRAM_ID --role admin
```

5. Check with `curl -sS https://app.example.com/api/health`. The body should include `"integration":"connected"`.
