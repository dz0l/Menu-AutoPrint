# Menu AutoPrint

Django/PostgreSQL version of Menu AutoPrint, a tool for creating bilingual menus, maintaining a dish database, and generating print-ready PDF output.

Repository: `https://github.com/dz0l/Menu-AutoPrint`

## Local Docker Run

1. Create the environment file:

```bash
cp .env.example .env
```

2. Start the services:

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py bootstrap_editor --username mAdmin --password qwerty123
docker compose exec web python manage.py collectstatic --noinput
```

3. Open the application:

```text
http://localhost/
```

Default editor account: `mAdmin` / `qwerty123`.
The password must be changed after the first login.

## Ubuntu Installation From GitHub

```bash
curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash
```

The installer clones or updates the repository, creates `.env` if needed, adds the detected server IP to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`, builds Docker services, runs migrations, creates the bootstrap editor, and collects static files.

If the app returns `Bad Request (400)` after changing the server address, add the address to `.env`:

```env
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,YOUR_SERVER_IP_OR_DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=http://YOUR_SERVER_IP_OR_DOMAIN
```

Then recreate the web containers:

```bash
cd /opt/menu-autoprint
docker compose up -d --force-recreate web nginx
```

Do not commit the real `.env` file. Keep real IP addresses, domains, database passwords, and `DJANGO_SECRET_KEY` only on the target server.

## Import The Old CSV Database

After the containers are running:

```bash
docker compose exec web python manage.py import_dishes_csv /path/to/calories.csv --dry-run
docker compose exec web python manage.py import_dishes_csv /path/to/calories.csv
```
