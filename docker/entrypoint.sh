#!/bin/sh
# Migrationen laufen beim Start (ARCHITECTURE.md §8) - eine Quelle für das Schema.
set -e

echo "→ alembic upgrade head"
alembic upgrade head

# Bring!-Katalog einmalig cachen; ohne Netz einfach weiter (der Katalog ist optional).
if [ ! -f "${MEALPLAN_DATA_DIR:-/data}/catalog/catalog.de-DE.json" ]; then
  echo "→ Bring!-Katalog laden"
  python -m mealplan.cli.main catalog-refresh || echo "  (übersprungen)"
fi

exec "$@"
