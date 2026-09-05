# Toutes les commandes Compose se lancent depuis src/ : voir l'article précédent.
COMPOSE = cd src && docker compose --env-file ../.env

# check_envvars.py analyse le DOSSIER src/, pas la chaîne COMPOSE_FILE. Il ignore
# donc ../docker-compose.override.yml et signale WEB_BIND_IP comme orpheline, alors
# qu'elle y est bien utilisée. Les S3_BACKUP_* ne sont lues que par
# ./scripts/backup-storage.sh, qui n'est pas un fichier Compose : même cas de figure.
# DEBUG_QGIS_WORKER_HOST_PATH, elle, est sans emploi.
IGNORED_VARS = DEBUG_QGIS_WORKER_HOST_PATH WEB_BIND_IP STORAGE_API_BIND_IP STORAGE_CONSOLE_BIND_IP SMTP4DEV_BIND_IP WEBDAV_BIND_IP S3_BACKUP_ENDPOINT S3_BACKUP_ACCESS_KEY S3_BACKUP_SECRET_KEY S3_BACKUP_BUCKET

.PHONY: up down config ps logs migrate check sauvegarde restore-test

up:      ; $(COMPOSE) up -d --build
down:    ; $(COMPOSE) down
config:  ; $(COMPOSE) config -q
ps:      ; $(COMPOSE) ps
logs:    ; $(COMPOSE) logs -f $(S)
migrate: ; $(COMPOSE) exec app python manage.py migrate
check:   ; python3 src/scripts/check_envvars.py .env --docker-compose-dir src --ignored-varnames $(IGNORED_VARS)

# La crontab appelle `make -C /opt/docker/qfieldcloud-stack sauvegarde`, jamais le
# script directement : l'emplacement de scripts/ reste un détail interne, qu'on
# peut déplacer sans casser une ligne de crontab qui ne préviendrait personne.
# `-C` fait entrer make dans le dossier : les chemins ci-dessous sont relatifs.
sauvegarde:   ; ./scripts/backup-storage.sh
restore-test: ; ./scripts/restore-test.sh
