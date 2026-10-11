#!/bin/sh
# Copia de seguridad diaria de la base de datos y las imágenes de Bioyologic.
# Programarla con cron (crontab -e):
#   30 3 * * * /home/ubuntu/bioyologic/deploy/backup.sh >> /home/ubuntu/backup.log 2>&1
set -eu
cd "$(dirname "$0")"
DEST="${BACKUP_DIR:-$HOME/backups}"
STAMP=$(date +%Y-%m-%d)
mkdir -p "$DEST"
# Copia consistente de SQLite aunque el servidor esté escribiendo.
docker compose exec -T bioyologic python -c \
  "import sqlite3; s=sqlite3.connect('/data/bioyologic.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
tar -czf "$DEST/bioyologic-$STAMP.tar.gz" --exclude=bioyologic.db -C data .
rm -f data/backup.db
# Conserva las copias de los últimos 14 días.
find "$DEST" -name 'bioyologic-*.tar.gz' -mtime +14 -delete
echo "Copia creada: $DEST/bioyologic-$STAMP.tar.gz"
