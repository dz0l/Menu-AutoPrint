# Menu AutoPrint

Django/PostgreSQL-приложение для сборки двуязычных меню, ведения базы блюд и формирования PDF для печати.

Репозиторий: `https://github.com/dz0l/Menu-AutoPrint`

English version: [README.EN.MD](README.EN.MD)

## Установка на Ubuntu

```bash
curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash
```

Скрипт клонирует или обновляет репозиторий, при необходимости создаёт `.env`, генерирует `DJANGO_SECRET_KEY` и `POSTGRES_PASSWORD`, подставляет адрес сервера, при необходимости добавляет текущего пользователя в группу `docker`, собирает Docker-сервисы, выполняет миграции, создаёт первого администратора (если его ещё нет) и выводит сводку установки с ошибками и рекомендациями.



В интерактивном режиме скрипт запрашивает логин и пароль администратора. 

Новый пароль: не менее 8 символов, одна заглавная буква и один спецсимвол.

Для неинтерактивной установки передайте учётные данные первого администратора через переменные окружения:

```bash
curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | \
  REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git \
  MENU_AUTOPRINT_ADMIN_USERNAME=mAdmin \
  MENU_AUTOPRINT_NEW_USER_PASSWORD='Strong!Pass123' \
  bash
```



## Полное удаление

Остановить контейнеры, удалить тома и образы проекта:

```bash
cd /opt/menu-autoprint
bash scripts/uninstall_ubuntu.sh --yes
```

Также удалить каталог приложения:

```bash
bash scripts/uninstall_ubuntu.sh --remove-app-dir --yes
```

Удалить Docker Engine с хоста (разрушительно; затрагивает все контейнеры на сервере):

```bash
bash scripts/uninstall_ubuntu.sh --remove-app-dir --remove-docker --yes
```



## Пользователи

Создать администратора:

```bash
cd /opt/menu-autoprint
docker compose exec -it web python manage.py create_staff_user mAdmin --role admin
```

Создать пользователя:

```bash
cd /opt/menu-autoprint
docker compose exec -it web python manage.py create_staff_user editor1 --role user
```

Неинтерактивный запуск:

```bash
cd /opt/menu-autoprint
MENU_AUTOPRINT_NEW_USER_PASSWORD='Strong!Pass123' \
  docker compose exec -T -e MENU_AUTOPRINT_NEW_USER_PASSWORD \
  web python manage.py create_staff_user mAdmin --role admin
```

Сбросить пароль и роль существующего пользователя:

```bash
cd /opt/menu-autoprint
docker compose exec -it web python manage.py create_staff_user mAdmin --role admin --update
docker compose exec web python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

Администраторов создают при установке или через SSH. В веб-интерфейсе «Пользователи» создаются только пользователи (роль `user`); повысить до администратора через GUI нельзя.

## Сеть и HTTPS

По умолчанию развёртывание идёт через профиль `caddy` в режиме LAN/HTTP:

```bash
.env:
COMPOSE_PROFILES=caddy
CADDY_SITE_ADDRESS=:80
CADDY_BIND_ADDRESS=0.0.0.0
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443
DJANGO_ENABLE_HTTPS=0
```

Открывайте приложение по адресу `http://ip-сервера/`.

Для публичного HTTPS через Caddy порты хоста `80` и `443` должны быть свободны для Caddy:

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

Если HTTPS закрывает внешний certbot или reverse proxy на хосте, отключите Caddy и опубликуйте внутренний nginx только на локальном порту. Docker не займёт порты хоста `80` и `443`:

```bash
.env:
COMPOSE_PROFILES=external-proxy
EXTERNAL_PROXY_BIND_ADDRESS=127.0.0.1
EXTERNAL_PROXY_HTTP_PORT=8080
DJANGO_ENABLE_HTTPS=1
DJANGO_ALLOWED_HOSTS=your-domain.tld
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.tld
```

Настройте reverse proxy хоста на `http://127.0.0.1:8080/` и передавайте `X-Forwarded-Proto: https`.  
Этот режим сам по себе не отдаёт публичный HTTPS: на `80`/`443` должен слушать proxy на хосте.

Если публикуете обычный HTTP на нестандартном порту, открывайте `http://ip-сервера:порт/`.

```bash
docker compose up -d --build --remove-orphans
```

При смене `COMPOSE_PROFILES=caddy` ↔ `COMPOSE_PROFILES=external-proxy` удалите сервис предыдущего профиля:

```bash
docker compose --profile caddy rm -sf caddy
docker compose --profile external-proxy rm -sf nginx-public
docker compose up -d --build --remove-orphans
```



## Импорт CSV с пути на сервере

По умолчанию положите CSV на хост в `/opt/menu-autoprint/path/` (например `/opt/menu-autoprint/path/calories.csv`), затем скопируйте в контейнер `web`:

```bash
cd /opt/menu-autoprint
WEB_ID="$(docker compose ps -q web)"
docker cp /opt/menu-autoprint/path/calories.csv "${WEB_ID}:/tmp/calories.csv"
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --dry-run
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv
```

Импорт больших файлов может занять 1–3 минуты.

```bash
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --apply-updates
```

Полная замена текущей таблицы блюд содержимым CSV:

```bash
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --replace-all --dry-run
docker compose exec web python manage.py import_dishes_csv /tmp/calories.csv --replace-all
```



## Архив PDF меню

Сформированные PDF (обычная печать, не альтернативная HTML; только учётные записи администратора) хранятся в `media/menu_archive/`. 

В один календарный день могут быть отдельные строки по локациям; повторная печать с той же датой + локацией + типом меню перезаписывает файл. 

Серверные подложки лежат в `media/menu_covers/` 

Раздел **Архив** показывает список для скачивания пользователям и администраторам. Файлы старше 730 дней удаляются автоматически; 

вручную:

```bash
cd /opt/menu-autoprint
docker compose exec web python manage.py purge_menu_archive
```



## Обслуживание

```bash
cd /opt/menu-autoprint
git pull
docker compose up -d --build web
```

Ручной бэкап PostgreSQL:

```bash
cd /opt/menu-autoprint
docker compose run --rm backup sh /scripts/backup_postgres.sh once
```

Автоперевод в редакторе базы включается заполнением `AZURE_TRANSLATOR_KEY` в `.env`; для ресурса Azure Translator в West Europe используйте `AZURE_TRANSLATOR_REGION=westeurope` и оставьте `AZURE_TRANSLATOR_ENDPOINT=https://api.cognitive.microsofttranslator.com`. После изменения `.env` перезапустите `web`.