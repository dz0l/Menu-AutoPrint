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

Файлы архива и подложек (`media/`) не отдаются напрямую через nginx: скачивание архива и превью подложек идут через приложение под логином.

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

В один календарный день могут быть отдельные строки по локациям. Повторная печать с той же датой, локацией и типом меню у администратора сначала спрашивает подтверждение в браузере (и на телефоне); после согласия файл перезаписывается, после отказа архив не меняется. Альтернативная HTML-печать архив не трогает. 

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

Контейнер `web` при старте выполняет `migrate` и `collectstatic` (`scripts/start_web.sh`).

Лимит попыток входа хранится в файловом кэше Django (`FileBasedCache`) с блокировкой на файл счётчика. При нескольких worker-процессах за общим nginx/прокси лимит по-прежнему действует на уровне процесса и общего каталога кэша; для жёсткой общей квоты между хостами нужен общий cache backend (например Redis). `REMOTE_ADDR` за reverse proxy обычно указывает на прокси, а не на клиента.

Штатный backup сохраняет **только PostgreSQL**. Том `media_data` (PDF архива и подложки) в эту копию **не** входит.

Если Docker Hub / CDN зависает на скачивании слоёв, а локальный образ `web` уже есть, можно обновить **только код** приложения без pull базовых образов:

```bash
cd /opt/menu-autoprint
git pull
bash scripts/update_web_code.sh
```

Скрипт собирает `Dockerfile.code` поверх текущего локального образа, пересоздаёт `web`, выполняет миграции. Новые pip/apt-зависимости таким способом **не** ставятся — при изменении `requirements.txt` или основного `Dockerfile` нужна обычная полная сборка, когда Hub снова доступен.

Ручной бэкап PostgreSQL:

```bash
cd /opt/menu-autoprint
docker compose run --rm backup bash /scripts/backup_postgres.sh once
```

Автоперевод в редакторе базы включается заполнением `AZURE_TRANSLATOR_KEY` в `.env`; для ресурса Azure Translator в West Europe используйте `AZURE_TRANSLATOR_REGION=westeurope` и оставьте `AZURE_TRANSLATOR_ENDPOINT=https://api.cognitive.microsofttranslator.com`. После изменения переменных в `.env` пересоздайте контейнер (`docker compose up -d`), обычный `docker compose restart web` environment не перечитывает.

Публикация `127.0.0.1:8000` на хост по умолчанию отключена (достаточно Docker DNS `web:8000`). Если нужен loopback-порт для редкого host-network peer: `docker compose -f docker-compose.yml -f docker-compose.host-port.example.yml up -d`.

Второй сайт Caddy (`CADDY_EXTRA_SITE_ADDRESS` / `CADDY_EXTRA_UPSTREAM`): либо не задавайте обе переменные, либо задайте обе с реальными значениями. Пустая строка в `CADDY_EXTRA_SITE_ADDRESS` ломает старт Caddy; entrypoint снимает пустые значения.

## Integration API

Узкий серверный HTTP API (`/api/integration/v1/`) для внешних систем. По умолчанию выключен и не влияет на обычный вход в веб-интерфейс. Модуль `apps/integrations/` и общий `apps/menu/document.py` обязательны в поставке даже при `INTEGRATION_API_ENABLED=0` (settings/urls импортируют пакет).

1. Создайте служебную учётную запись и ключ:

```bash
docker compose exec web python manage.py create_integration_credential --username integration-service
```

2. Запишите в `.env` выведенные `INTEGRATION_API_ENABLED=1`, `INTEGRATION_SERVICE_USER_ID` и `INTEGRATION_API_KEY_HASH`. Сырой ключ покажите один раз клиенту интеграции; в `.env` храните только hash.

3. Пересоздайте `web` (`docker compose up -d`), чтобы подтянуть environment. Запросы с заголовком `Authorization: Bearer <ключ>`.

`POST /api/integration/v1/menu/archive-status` только сообщает, есть ли уже файл с той же датой, подложкой и типом (`exists`, `display_name`), и ничего не записывает. `POST /api/integration/v1/menu/pdf` по-прежнему перезаписывает такой файл без отдельного вопроса: клиент сам решает, вызывать ли проверку заранее.

Истёкшие integration-операции удаляются порциями при новых запросах (до 200 за проход); отдельного cron нет. Лимит тела Django (~20 МБ) не заменяет отдельный лимит частоты тяжёлых PDF.

Cookie-сессия браузера к этому namespace не допускается. Ключ не открывает `/admin/` и обычные browser API.

## Необязательный бот Telegram

Бот с мини-приложением не входит в стандартный `docker compose` этого репозитория. Его ставят отдельным сервисом в сеть `menu-autoprint_default` (имя сервиса `menu-telegram`, порт `8090` только внутри Docker). Как пользоваться — раздел 12 в [GUIDE.MD](GUIDE.MD).

Кратко для запуска рядом с уже работающим сайтом:

1. Включите Integration API командой выше. Сырой ключ запишите боту в `MENU_API_CREDENTIAL`; в `.env` сайта остаётся только hash.
2. У бота задайте `MENU_API_BASE_URL=http://web:8000/api/integration/v1`, публичный `PUBLIC_MINI_APP_URL` с `https://`, токен бота и `SESSION_SECRET`, затем `docker compose up -d --build` в каталоге бота.
3. Если мини-приложение отдаёт Caddy этого сервера, в `.env` сайта укажите оба значения и пересоздайте контейнеры (`docker compose up -d`):

```bash
CADDY_EXTRA_SITE_ADDRESS=app.example.com
CADDY_EXTRA_UPSTREAM=menu-telegram:8090
```

4. Пользователь отправляет боту `/start`. Первый администратор:

```bash
docker compose exec menu-telegram python -m backend.cli approve TELEGRAM_ID --role admin
```

5. Проверка: `curl -sS https://app.example.com/api/health` — в ответе `"integration":"connected"`.