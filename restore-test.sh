#!/usr/bin/env bash
# Restaure le dernier dump dans une base jetable et compare les effectifs.
# Une sauvegarde dont on n'a jamais tente la restauration n'est pas une
# sauvegarde : c'est un fichier.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DUMP="$(ls -1t "${STACK_DIR}"/backups/db/*.dump | head -1)"
echo "Dump teste : $(basename "${DUMP}")"

docker exec qfieldcloud-db-1 sh -c "
set -e
psql -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS restauration_test' >/dev/null
psql -U \"\$POSTGRES_USER\" -d postgres -c 'CREATE DATABASE restauration_test' >/dev/null
pg_restore -U \"\$POSTGRES_USER\" -d restauration_test --no-owner --no-privileges \
  /backups/db/$(basename "${DUMP}")
echo
printf '%-22s %-10s %-10s %s\n' table production restauree ecart
for t in core_user project_project core_job filestorage_file filestorage_fileversion; do
  A=\$(psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM \$t\" 2>/dev/null || echo '-')
  B=\$(psql -U \"\$POSTGRES_USER\" -d restauration_test -tAc \"SELECT count(*) FROM \$t\" 2>/dev/null || echo '-')
  printf '%-22s %-10s %-10s %s\n' \"\$t\" \"\$A\" \"\$B\" \"\$([ \"\$A\" = \"\$B\" ] && echo OK || echo ECART)\"
done
echo
echo -n 'PostGIS dans la base restauree : '
psql -U \"\$POSTGRES_USER\" -d restauration_test -tAc \"SELECT extversion FROM pg_extension WHERE extname='postgis'\"
psql -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE restauration_test' >/dev/null
echo 'Base jetable supprimee.'
"
