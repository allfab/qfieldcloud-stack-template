#!/usr/bin/env bash
# Miroir local du bucket objet + copie du .env.
#
# Pourquoi pas ofelia, alors qu'il ordonnance deja le dump de la base ?
# Deux raisons, verifiees sur la 0.3.18 :
#   1. un job `job-run` declare par label n'est JAMAIS enregistre (aucune
#      erreur, il n'apparait simplement pas dans "New job registered") ;
#   2. les labels sont lisibles par `docker inspect` : y mettre la cle secrete
#      du stockage objet reviendrait a la publier a tout le monde sur l'hote.
# D'ou ce script, lance par la crontab de l'utilisateur.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${STACK_DIR}/backups"
RETENTION_DAYS=14

# shellcheck disable=SC1091
set -a; source "${STACK_DIR}/.env"; set +a

mkdir -p "${BACKUP_DIR}/storage" "${BACKUP_DIR}/env"

# 1. Le bucket. `--remove` fait du miroir un reflet fidele : un objet supprime
#    en amont disparait de la copie. C'est voulu — la protection contre la
#    suppression accidentelle, c'est PBS qui l'assure, avec son historique.
docker run --rm \
  -v "${BACKUP_DIR}/storage:/mirror" \
  --entrypoint sh minio/mc:latest -c "
    mc alias set garage '${GARAGE_BACKUP_ENDPOINT}' '${GARAGE_BACKUP_ACCESS_KEY}' '${GARAGE_BACKUP_SECRET_KEY}' --api S3v4 >/dev/null
    mc mirror --overwrite --remove 'garage/${GARAGE_BACKUP_BUCKET}' /mirror
    mc du /mirror
  "

# 2. Le .env. Sans SECRET_KEY et SALT_KEY, les champs chiffres de la base
#    restituee sont illisibles : la sauvegarde des deux autres ne vaut rien
#    sans celle-ci.
install -m 600 "${STACK_DIR}/.env" "${BACKUP_DIR}/env/env-$(date +%Y%m%d-%H%M)"
find "${BACKUP_DIR}/env" -name 'env-*' -mtime "+${RETENTION_DAYS}" -delete

# 3. Un etat lisible, pour que la supervision ait quelque chose a regarder.
{
  echo "date        : $(date -Is)"
  echo "objets      : $(find "${BACKUP_DIR}/storage" -type f | wc -l)"
  echo "taille      : $(du -sh --apparent-size "${BACKUP_DIR}/storage" | cut -f1)"
  echo "dumps base  : $(find "${BACKUP_DIR}/db" -name '*.dump' | wc -l)"
  echo "dernier dump: $(ls -1t "${BACKUP_DIR}/db"/*.dump 2>/dev/null | head -1 | xargs -r basename)"
} > "${BACKUP_DIR}/derniere-sauvegarde.txt"
cat "${BACKUP_DIR}/derniere-sauvegarde.txt"
