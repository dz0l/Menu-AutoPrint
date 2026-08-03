# Menu AutoPrint

Django/PostgreSQL version of Menu AutoPrint for building bilingual menus, maintaining the dish database, and generating print-ready PDF files.

Repository: `https://github.com/dz0l/Menu-AutoPrint`

## Ubuntu Installation

```bash
curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash
```

The installer clones or updates the repository, creates `.env` if needed, generates `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`, configures the detected server address, adds the current user to the `docker` group when needed, builds Docker services, runs migrations, creates the first admin account if none exists, and prints an installation summary with errors and recommendations.

If Docker reports `permission denied` after installation, log out and back in, or run `newgrp docker`.

During interactive installation the script asks for the admin username and password. The default username prompt is `mAdmin`, but the password is not stored in the script.

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

Create an editor user:

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

## Menu PDF archive

Generated PDFs (normal print mode, not alternate HTML print) are stored under `media/menu_archive/` as `YYYY-MM-DD_main.pdf` / `_breakfast.pdf` (and `_banquet` when used). Opening **Архив** in the app lists downloads for editors. Files older than 730 days are removed automatically; you can also run:

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

Create a manual PostgreSQL backup:

```bash
cd /opt/menu-autoprint
docker compose run --rm backup sh /scripts/backup_postgres.sh once
```

Enable editor auto-translation by filling `AZURE_TRANSLATOR_KEY` in `.env`; use `AZURE_TRANSLATOR_REGION=westeurope` for a West Europe Azure Translator resource and keep `AZURE_TRANSLATOR_ENDPOINT=https://api.cognitive.microsofttranslator.com` for text translation. Restart `web` after changing `.env`.
