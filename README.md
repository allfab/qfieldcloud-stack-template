# qfieldcloud-stack — squelette de deploiement QFieldCloud

Depot **template** pour monter une instance QFieldCloud auto-hebergee sans jamais
modifier une ligne du depot upstream.

Le principe tient en une phrase : `opengisch/QFieldCloud` est un **sous-module**
epingle sur un tag, en lecture seule ; tout ce qui vous appartient vit ici, un cran
au-dessus. `git -C src status` doit rester vide en permanence — c'est le controle
qui dit si vous avez contracte une dette.

## Ce que contient ce depot

| Fichier | Role |
|---|---|
| `src/` | Sous-module `opengisch/QFieldCloud`, epingle sur un tag |
| `.env.template` | Modele de configuration. **A copier en `.env`**, qui n'est jamais versionne |
| `docker-compose.override.yml` | Le seul fichier Compose qui vous appartient. Charge en dernier |
| `Makefile` | Raccourcis, pour ne plus se demander d'ou lancer Compose |
| `.gitignore` | Exclut `.env` — il contient vos secrets |

## Demarrage, d'un dossier vide a une instance qui repond

Si vous etes passe par le bouton **« Use this template »**, votre depot est deja vierge :
clonez-le et sautez l'etape 0.

```bash
# 0. Repartir d'un historique a vous
#    Les commits de ce depot racontent MON instance (mon frontal, mes IP). Le votre
#    doit raconter la votre : c'est tout l'interet du montage.
git clone https://github.com/allfab/qfieldcloud-stack-template.git qfieldcloud-stack
cd qfieldcloud-stack
rm -rf .git src        # src/.git pointe dans .git/modules/ : les deux partent ensemble
git init

# 1. Le socle
git submodule add -b release https://github.com/opengisch/QFieldCloud.git src
git -C src checkout v26.26          # choisissez le tag, ne restez pas sur une branche

# 2. Les dossiers que Docker creerait en root si on ne le prenait pas de vitesse
mkdir -p src/conf/certbot src/conf/nginx/config.d

# 3. Votre configuration
cp .env.template .env
$EDITOR .env                        # voir « Les variables a changer » ci-dessous
make check                          # valide le .env contre les fichiers Compose
make config                         # valide la configuration Compose fusionnee

# 4. Les images QGIS, une par une : elles sont enormes
cd src
alias dc='docker compose --env-file ../.env'
dc build qgis3 && docker builder prune -f && df -h /
dc build qgis4 && docker builder prune -f && df -h /
cd ..

# 5. La mise en service
make up
cd src
dc exec app python manage.py migrate
dc run --rm app python manage.py collectstatic --noinput
dc exec --user root app python manage.py compilemessages
dc exec app python manage.py createsuperuser
```

Au premier `up`, quatre services sortent en `Exited (0)` — c'est normal, ils ont fait
leur travail — et `worker_wrapper` boucle sur `relation "project_project" does not
exist` jusqu'au `migrate`. Voir la section « pieges » plus bas.

## Les variables a changer

Toutes sont marquees `change_me` ou pointent vers `example.org` dans le template.

| Variable | Remarque |
|---|---|
| `QFIELDCLOUD_HOST` | Sans schema, sans port, sans slash |
| `DJANGO_ALLOWED_HOSTS` | Doit contenir `QFIELDCLOUD_HOST` |
| `SECRET_KEY`, `SALT_KEY` | 64 caracteres tires au sort. **Sans eux, les champs chiffres de la base sont perdus** : ils font partie de votre sauvegarde |
| `POSTGRES_PASSWORD`, `OBJECT_STORAGE_ROOT_*`, `WEBDAV_PASSWORD` | idem |
| `STORAGES` | `access_key`/`secret_key` doivent etre alignes sur `OBJECT_STORAGE_ROOT_*`, sinon `createbuckets` echoue |
| `WEB_BIND_IP` | **Non upstream** : ou publier le port HTTPS. `127.0.0.1` si le frontal est sur cette machine, l'IP de l'hote s'il est ailleurs |
| `LETSENCRYPT_EMAIL` | `LETSENCRYPT_STAGING` reste a `1` tant que le DNS public ne pointe pas ici |
| `QFIELDCLOUD_ACCOUNT_ADAPTER` | **A ne pas oublier.** Defaut upstream `...AccountAdapterSignUpOpen` : n'importe qui trouvant votre URL peut se creer un compte. `...AccountAdapterSignUpClosed` bascule en mode sur invitation (les invitations continuent de marcher, l'admin Django aussi) |
| `QFIELDCLOUD_DEFAULT_TIME_ZONE` | Defaut upstream : `Europe/Zurich` |

## Les trois pieges qui coutent une soiree

**1. `COMPOSE_FILE` livre par l'upstream est un profil de developpement.** Le template
charge `standalone` + `prod` + votre override :

```
COMPOSE_FILE=docker-compose.yml:docker-compose.override.standalone.yml:docker-compose.override.prod.yml:../docker-compose.override.yml
```

Les trois premiers appartiennent au sous-module et seront remplaces a l'identique au
prochain `git checkout`. Le quatrieme est a vous, d'ou le `../`.

**2. En `DEBUG=0`, les workers doivent passer par nginx.** Le defaut upstream
`QFIELDCLOUD_WORKER_QFIELDCLOUD_URL=http://app:8000/api/v1/` court-circuite nginx,
donc pas de `X-Forwarded-For`, donc `500` sur **tous** les telechargements de fichiers
de projet. Le template corrige cela avec trois choses qui vont ensemble :
`NGINX_ALLOW_INTERNAL_HTTP=1`, un alias reseau `${QFIELDCLOUD_HOST}` sur `nginx` dans
l'override, et l'URL du worker qui passe par ce nom.

**3. `SMTP4DEV_SMTP_PORT` vaut `25` par defaut** et smtp4dev publie ce port sur toutes
les interfaces. Sur une Debian avec un agent de transport local, le demarrage echoue
sur un `address already in use` qui ne nomme pas le coupable. Verifiez avec
`ss -tlnp | grep ':25 '`.

## Monter de version

```bash
git -C src fetch --tags
git -C src checkout v26.27
make check && make config
make up
cd src && docker compose --env-file ../.env exec app python manage.py migrate
git add src && git commit -m "Montee en v26.27"
```

Le commit ne contient qu'un changement de pointeur de sous-module. C'est tout
l'interet du montage : rien a reporter a la main.

## Retirer un service upstream

On ne supprime pas un service du sous-module : on lui donne un **profil** que
personne n'active, depuis `docker-compose.override.yml`.

```yaml
  certbot:
    profiles: ["never"]
```

Le service disparait de `docker compose config --services`. Mais **`up -d
--remove-orphans` ne supprime pas le conteneur deja en marche** : Compose ne
considere pas comme orpheline une instance simplement exclue par un profil. Il
faut la nommer, en reactivant le profil le temps de la commande :

```bash
docker compose --env-file ../.env --profile never rm -sf certbot
```

Ce depot retire ainsi `certbot` (le TLS est termine par un frontal), puis
`rustfs` et `createbuckets` (le stockage objet est externalise). Si vous restez
en profil standalone, enlevez les deux dernieres lignes `profiles`.

## Sauvegarde

Trois choses, et trois seulement :

- la base — `pg_dump` logique ;
- le bucket du stockage objet — miroir S3 ;
- le `.env`, sans lequel les deux premiers sont inexploitables (`SECRET_KEY` et
  `SALT_KEY` dechiffrent les champs chiffres de la base).

Les grilles PROJ (~850 Mo) et les images sont integralement reconstructibles.

Deux ordonnanceurs, pour une raison precise :

| Quoi | Par qui | Quand |
|---|---|---|
| `pg_dump -Fc` + purge a 14 jours | **ofelia**, `job-exec` sur `db` (labels de l'override) | 02:30 |
| miroir du bucket + copie du `.env` | **crontab utilisateur**, `./backup-storage.sh` | 02:45 |

Pourquoi pas ofelia pour les deux : en 0.3.18, un job **`job-run` declare par
label n'est jamais enregistre** — aucune erreur, il n'apparait simplement pas
dans les `New job registered` du journal. Et les labels sont lisibles par
`docker inspect` : la cle secrete du stockage objet n'a rien a y faire.

Les fichiers atterrissent dans `backups/` (ignore par git), d'ou la sauvegarde
du conteneur les emporte hors machine.

### Tester la restauration

```bash
./restore-test.sh
```

Restaure le dernier dump dans une base jetable, compare les effectifs table par
table avec la production, verifie que PostGIS est bien la, puis supprime la base.
Une sauvegarde dont on n'a jamais tente la restauration n'est pas une sauvegarde.
