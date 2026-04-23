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

3. application:

```text
http://localhost/
```

Default editor account: `mAdmin` / `qwerty123`.
The password must be changed after the first login.

## Ubuntu Installation From GitHub

```bash
REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash scripts/install_ubuntu.sh
```

The installer clones or updates the repository, creates `.env` if needed, builds Docker services, runs migrations, creates the bootstrap editor, and collects static files.

## Import The Old CSV Database

After the containers are running:

```bash
docker compose exec web python manage.py import_dishes_csv /path/to/calories.csv --dry-run
docker compose exec web python manage.py import_dishes_csv /path/to/calories.csv
```
