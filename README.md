# Menu AutoPrint

Django/PostgreSQL версия проекта для формирования и печати меню.

## Локальный запуск через Docker

1. Копирование окружения:

```bash
cp .env.example .env
```

2. Запуск сервисов:

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py bootstrap_editor --username mAdmin --password qwerty123
docker compose exec web python manage.py collectstatic --noinput
```

3. `http://localhost/`.

Стартовый редактор: `mAdmin` / `qwerty123`. После входа требуется сменить пароль.

## Установка из GitHub

```bash
REPO_URL=https://github.com/<user>/<repo>.git bash scripts/install_ubuntu.sh
```

## Импорт старой CSV-базы

После запуска контейнеров:

```bash
docker compose exec web python manage.py import_dishes_csv /path/to/calories.csv --dry-run
docker compose exec web python manage.py import_dishes_csv /path/to/calories.csv
```

