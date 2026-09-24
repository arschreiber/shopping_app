#!/bin/sh
# Nächtliches Backup (ARCHITECTURE.md §8). Die Gerichteliste ist die Handarbeit von zwei
# Abenden - sie soll nicht am NAS-Snapshot hängen.
#
# In die Crontab des Hosts:
#   0 3 * * * docker compose exec -T app /app/docker/backup.sh
set -e

DATA_DIR="${MEALPLAN_DATA_DIR:-/data}"
KEEP="${MEALPLAN_BACKUP_KEEP:-7}"
TARGET="$DATA_DIR/backups/mealplan-$(date +%Y%m%d-%H%M%S).sqlite3"

mkdir -p "$DATA_DIR/backups"
# .backup statt cp: konsistent auch bei laufenden Schreibvorgängen (WAL).
sqlite3 "$DATA_DIR/mealplan.sqlite3" ".backup '$TARGET'"
gzip -f "$TARGET"
echo "Backup: $TARGET.gz"

# Nur die letzten $KEEP Generationen behalten.
ls -1t "$DATA_DIR"/backups/mealplan-*.sqlite3.gz 2>/dev/null \
  | tail -n +$((KEEP + 1)) \
  | xargs -r rm -f
