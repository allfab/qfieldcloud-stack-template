#!/usr/bin/env bash
# Miroir local du bucket objet + copie du .env.
#
# Rien ici n'est propre à un fournisseur : c'est du `mc mirror` S3 standard, qui
# marche aussi bien sur le rustfs du profil standalone que sur un cluster
# externe. Seules les quatre variables S3_BACKUP_* changent.
#
# Pourquoi pas ofelia, alors qu'il ordonnance déjà le dump de la base ?
# Deux raisons, vérifiées sur la 0.3.18 :
#   1. un job `job-run` déclaré par label n'est JAMAIS enregistré (aucune
#      erreur, il n'apparaît simplement pas dans "New job registered") ;
#   2. les labels sont lisibles par `docker inspect` : y mettre la clé secrète
#      du stockage objet reviendrait à la publier à tout le monde sur l'hôte.
# D'où ce script, lancé par la crontab de l'utilisateur.
set -euo pipefail

# La racine du dépôt, pas scripts/ : c'est là que vivent .env et backups/.
STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${STACK_DIR}/backups"
RETENTION_DAYS=14

# shellcheck disable=SC1091
set -a; source "${STACK_DIR}/.env"; set +a

# Les quatre variables ci-dessous ne servent qu'ici, jamais à l'application.
# Sans ce garde-fou, une variable oubliée sort en "unbound variable" et une
# valeur laissée à `change_me` en échec de connexion mc — deux messages qui ne
# nomment pas le coupable. Voir la section "Sauvegarde du stockage objet" du
# .env.template, qui donne aussi les valeurs pour le profil standalone.
missing=""
for v in S3_BACKUP_ENDPOINT S3_BACKUP_ACCESS_KEY S3_BACKUP_SECRET_KEY S3_BACKUP_BUCKET; do
  value="${!v-}"
  case "${value}" in
    ""|*change_me*) missing="${missing} ${v}" ;;
  esac
done
if [ -n "${missing}" ]; then
  echo "Sauvegarde du bucket impossible : à renseigner dans .env :${missing}" >&2
  echo "Voir la section \"Sauvegarde du stockage objet\" de .env.template." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}/storage" "${BACKUP_DIR}/env"

# 1. Le bucket. `--remove` fait du miroir un reflet fidèle : un objet supprimé
#    en amont disparaît de la copie. C'est voulu, mais cela suppose que QUELQUE
#    CHOSE garde un historique de ce dossier — ici PBS, qui sauvegarde le
#    conteneur. Sans cet historique derrière, ce miroir ne protège PAS d'une
#    suppression accidentelle : il la recopie fidèlement. Retirez `--remove`
#    si vous n'avez rien de tel.
docker run --rm \
  -v "${BACKUP_DIR}/storage:/mirror" \
  --entrypoint sh minio/mc:latest -c "
    mc alias set backup '${S3_BACKUP_ENDPOINT}' '${S3_BACKUP_ACCESS_KEY}' '${S3_BACKUP_SECRET_KEY}' --api S3v4 >/dev/null
    mc mirror --overwrite --remove 'backup/${S3_BACKUP_BUCKET}' /mirror
    mc du /mirror
  "

# 2. Le .env. Sans SECRET_KEY et SALT_KEY, les champs chiffrés de la base
#    restituée sont illisibles : la sauvegarde des deux autres ne vaut rien
#    sans celle-ci.
install -m 600 "${STACK_DIR}/.env" "${BACKUP_DIR}/env/env-$(date +%Y%m%d-%H%M)"
find "${BACKUP_DIR}/env" -name 'env-*' -mtime "+${RETENTION_DAYS}" -delete

# 3. Un état lisible, pour que la supervision ait quelque chose à regarder.
{
  echo "date        : $(date -Is)"
  echo "objets      : $(find "${BACKUP_DIR}/storage" -type f | wc -l)"
  echo "taille      : $(du -sh --apparent-size "${BACKUP_DIR}/storage" | cut -f1)"
  echo "dumps base  : $(find "${BACKUP_DIR}/db" -name '*.dump' | wc -l)"
  echo "dernier dump: $(ls -1t "${BACKUP_DIR}/db"/*.dump 2>/dev/null | head -1 | xargs -r basename)"
} > "${BACKUP_DIR}/last-backup.txt"
cat "${BACKUP_DIR}/last-backup.txt"
