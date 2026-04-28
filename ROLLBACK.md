# Backup and rollback

## Before updating production from 2.3.5

Create a git rollback point on the current production code:

```bash
git tag 2.3.5
git push origin 2.3.5
```

Create a one-shot PostgreSQL backup:

```bash
docker compose run --rm backup sh /scripts/backup_postgres.sh once
```

Backups are written to `./backups` on the host.

## Update test server

Use the test server first:

```bash
git pull
docker compose up -d --build web
```

The UI redesign does not add database migrations. Rollback should normally only require returning the code to `2.3.5`.

## Roll back code to 2.3.5

```bash
git fetch --tags
git checkout 2.3.5
docker compose up -d --build web
```

## Restore database only if needed

Use this only if data was changed and must be reverted. Replace the archive name with the backup file you want to restore:

```bash
gunzip -c backups/<backup-file>.sql.gz | docker compose exec -T db psql -U menu -d menu
```
