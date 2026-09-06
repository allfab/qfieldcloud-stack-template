# qfieldcloud-stack — squelette de déploiement QFieldCloud

Dépôt **template** pour monter une instance QFieldCloud auto-hébergée sans jamais
modifier une ligne du dépôt upstream.

Le principe tient en une phrase : `opengisch/QFieldCloud` est un **sous-module**
épinglé sur un tag, en lecture seule ; tout ce qui vous appartient vit ici, un cran
au-dessus. `git -C src status` doit rester vide en permanence — c'est le contrôle
qui dit si vous avez contracté une dette.

Cela vaut jusqu'à l'apparence : mettre son logo et ses couleurs sur la page de
connexion se fait depuis le dehors, par un module de réglages Django composé —
voir « Thème ».

**Ce template est livré avec un thème actif**, pas avec l'apparence d'origine de
QFieldCloud : le logo officiel, le bleu de la marque, le vert de QField et un
fond de courbes de niveau. Il sert deux fins — habiller une instance dès le
premier démarrage, et montrer jusqu'où va le principe du dehors, puisqu'il ne
coûte pas une ligne de `src/`. Il se retire en trois étapes, décrites à
« Revenir au thème de l'upstream » ; le nom affiché, lui, est un placeholder à
changer, `INSTANCE_NAME` dans `theme/settings_custom.py`.

## Ce que contient ce dépôt

| Fichier | Rôle |
|---|---|
| `src/` | Sous-module `opengisch/QFieldCloud`, épinglé sur un tag |
| `.env.template` | Modèle de configuration. **À copier en `.env`**, qui n'est jamais versionné |
| `docker-compose.override.yml` | Le seul fichier Compose qui vous appartient. Chargé en dernier |
| `Makefile` | Raccourcis, pour ne plus se demander d'où lancer Compose ni où vivent les scripts |
| `scripts/` | Sauvegarde du bucket et test de restauration. À appeler par le `Makefile` (`make backup`, `make restore-test`), pas directement |
| `theme/` | Apparence de l'instance : logos, couleurs, textes. **Livré actif.** Chargé par `DJANGO_SETTINGS_MODULE`, sans rien modifier dans `src/`. Voir « Thème » |
| `.gitignore` | Exclut `.env` — il contient vos secrets |

## Démarrage, d'un dossier vide à une instance qui répond

Si vous êtes passé par le bouton **« Use this template »**, votre dépôt est déjà vierge :
clonez-le et sautez l'étape 0.

```bash
# 0. Repartir d'un historique à vous
#    Les commits de ce dépôt racontent MON instance (mon frontal, mes IP). Le vôtre
#    doit raconter la vôtre : c'est tout l'intérêt du montage.
git clone https://github.com/allfab/qfieldcloud-stack-template.git qfieldcloud-stack
cd qfieldcloud-stack
rm -rf .git src        # src/.git pointe dans .git/modules/ : les deux partent ensemble
git init

# 1. Le socle
git submodule add -b release https://github.com/opengisch/QFieldCloud.git src
git -C src checkout v26.26          # choisissez le tag, ne restez pas sur une branche

# 2. Les dossiers que Docker créerait en root si on ne le prenait pas de vitesse
mkdir -p src/conf/certbot src/conf/nginx/config.d

# 3. Votre configuration
cp .env.template .env
$EDITOR .env                        # voir « Les variables à changer » ci-dessous
$EDITOR theme/settings_custom.py    # INSTANCE_NAME : le nom affiché de l'instance
make check                          # valide le .env contre les fichiers Compose
make config                         # valide la configuration Compose fusionnée

# 4. Les images QGIS, une par une : elles sont énormes
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
exist` jusqu'au `migrate`. Voir la section « pièges » plus bas.

## Conventions

Le code est en anglais — cibles du `Makefile`, variables, noms de fichiers, noms
de jobs Ofelia, bases de données — et la prose en français : commentaires,
messages affichés, documentation. C'est la convention la plus courante des dépôts
publics, et elle évite le mélange des deux dans une même ligne de commande.

## Les variables à changer

Toutes sont marquées `change_me` ou pointent vers `example.org` dans le template.

| Variable | Remarque |
|---|---|
| `QFIELDCLOUD_HOST` | Sans schéma, sans port, sans slash |
| `DJANGO_ALLOWED_HOSTS` | Doit contenir `QFIELDCLOUD_HOST` |
| `SECRET_KEY`, `SALT_KEY` | 64 caractères tirés au sort. **Sans eux, les champs chiffrés de la base sont perdus** : ils font partie de votre sauvegarde |
| `POSTGRES_PASSWORD`, `OBJECT_STORAGE_ROOT_*`, `WEBDAV_PASSWORD` | idem |
| `STORAGES` | `access_key`/`secret_key` doivent être alignés sur `OBJECT_STORAGE_ROOT_*`, sinon `createbuckets` échoue |
| `WEB_BIND_IP` | **Non upstream** : où publier le port HTTPS. `127.0.0.1` si le frontal est sur cette machine, l'IP de l'hôte s'il est ailleurs |
| `LETSENCRYPT_EMAIL` | `LETSENCRYPT_STAGING` reste à `1` tant que le DNS public ne pointe pas ici |
| `QFIELDCLOUD_ACCOUNT_ADAPTER` | **À ne pas oublier.** Défaut upstream `...AccountAdapterSignUpOpen` : n'importe qui trouvant votre URL peut se créer un compte. `...AccountAdapterSignUpClosed` bascule en mode sur invitation (les invitations continuent de marcher, l'admin Django aussi) |
| `QFIELDCLOUD_DEFAULT_TIME_ZONE` | Défaut upstream : `Europe/Zurich` |
| `S3_BACKUP_*` | **Non upstream** : lues uniquement par `scripts/backup-storage.sh`. Voir « Sauvegarde » |
| `SMTP4DEV_WEB_BIND_IP` | **Non upstream** : où publier l'interface web du piège à courriels. `127.0.0.1` par défaut ; voir le piège 3 avant d'y mettre une IP de LAN |
| `DJANGO_SETTINGS_MODULE` | Le point d'extension de **tous** les réglages Django. Le passer à `qfieldcloud.settings_custom` active `theme/` ; le laisser au défaut donne l'apparence upstream. Voir « Thème » |

## Les trois pièges qui coûtent une soirée

**1. `COMPOSE_FILE` livré par l'upstream est un profil de développement.** Le template
charge `standalone` + `prod` + votre override :

```
COMPOSE_FILE=docker-compose.yml:docker-compose.override.standalone.yml:docker-compose.override.prod.yml:../docker-compose.override.yml
```

Les trois premiers appartiennent au sous-module et seront remplacés à l'identique au
prochain `git checkout`. Le quatrième est à vous, d'où le `../`.

**2. En `DEBUG=0`, les workers doivent passer par nginx.** Le défaut upstream
`QFIELDCLOUD_WORKER_QFIELDCLOUD_URL=http://app:8000/api/v1/` court-circuite nginx,
donc pas de `X-Forwarded-For`, donc `500` sur **tous** les téléchargements de fichiers
de projet. Le template corrige cela avec trois choses qui vont ensemble :
`NGINX_ALLOW_INTERNAL_HTTP=1`, un alias réseau `${QFIELDCLOUD_HOST}` sur `nginx` dans
l'override, et l'URL du worker qui passe par ce nom.

**3. `SMTP4DEV_SMTP_PORT` vaut `25` par défaut** et smtp4dev publie ce port sur toutes
les interfaces. Sur une Debian avec un agent de transport local, le démarrage échoue
sur un `address already in use` qui ne nomme pas le coupable. Vérifiez avec
`ss -tlnp | grep ':25 '`.

Tant qu'on y est : **l'interface web de smtp4dev n'a aucune authentification**, et
elle donne accès aux liens de réinitialisation de mot de passe — donc à la prise de
contrôle des comptes. L'override publie ses trois ports séparément pour cette
raison :

```yaml
    ports: !override
      - "${SMTP4DEV_WEB_BIND_IP}:${SMTP4DEV_WEB_PORT}:80"
      - "127.0.0.1:${SMTP4DEV_SMTP_PORT}:25"
      - "127.0.0.1:${SMTP4DEV_IMAP_PORT}:143"
```

Seule l'interface web peut sortir sur le LAN, en renseignant `SMTP4DEV_WEB_BIND_IP`
— c'est la seule qu'on ait une raison d'ouvrir dans un navigateur. L'IMAP donne accès
aux mêmes messages et le SMTP accepterait n'importe quel envoi : ils restent sur le
loopback en dur. À `127.0.0.1`, l'accès se fait par un tunnel SSH :
`ssh -N -L 8012:127.0.0.1:8012 <hôte>`. La sortie définitive de ce compromis, c'est
un vrai relais SMTP — après quoi smtp4dev se retire par un profil.

## Monter de version

```bash
git -C src fetch --tags
git -C src checkout v26.27
make check && make config
make up
cd src && docker compose --env-file ../.env exec app python manage.py migrate
git add src && git commit -m "Montée en v26.27"
```

Le commit ne contient qu'un changement de pointeur de sous-module. C'est tout
l'intérêt du montage : rien à reporter à la main.

## Retirer un service upstream

On ne supprime pas un service du sous-module : on lui donne un **profil** que
personne n'active, depuis `docker-compose.override.yml`.

```yaml
  certbot:
    profiles: ["never"]
```

Le service disparaît de `docker compose config --services`. Mais **`up -d
--remove-orphans` ne supprime pas le conteneur déjà en marche** : Compose ne
considère pas comme orpheline une instance simplement exclue par un profil. Il
faut la nommer, en réactivant le profil le temps de la commande :

```bash
docker compose --env-file ../.env --profile never rm -sf certbot
```

Ce dépôt retire ainsi `certbot` (le TLS est terminé par un frontal), puis
`rustfs` et `createbuckets` (le stockage objet est externalisé). Si vous restez
en profil standalone, enlevez les deux dernières lignes `profiles`.

## Thème

Le dossier `theme/` porte l'apparence de l'instance. Rien n'est modifié dans
`src/` : `DJANGO_SETTINGS_MODULE` désigne un module à nous, qui importe les
réglages upstream et n'écrase que l'apparence.

```
theme/
  settings_custom.py          # WHITELABEL (pages publiques) + JAZZMIN_* (admin)
  contours.py                 # régénère static/contours.svg (outil de conception)
  static/                     # logos, favicon, theme.css -> servis sous custom/
  account-base.html           # gabarit recopié, + une ligne <link>
  account-base.html.upstream  # sa version d'origine, pour `make theme-diff`
```

Deux thèmes, parce que la racine du site redirige vers `/admin/` : `WHITELABEL`
habille `/accounts/…`, Jazzmin habille l'admin. Les deux se règlent dans
`settings_custom.py`.

### Le dessin

L'habillage reprend les codes de [qfield.cloud](https://qfield.cloud) : le logo
officiel, le bleu de la marque `#4a6fae`, le vert de QField `#80cc28` en accent,
et des courbes de niveau en filigrane derrière la page de connexion.

Le fond n'est pas une image trouvée quelque part : `theme/contours.py`
échantillonne un champ scalaire et en suit les lignes de niveau par marching
squares, comme une carte topographique. Le SVG produit est versionné — le script
n'est là que pour le rejouer autrement. Changer `SEED` donne un autre relief,
`LEVELS` l'équidistance des isolignes :

```bash
python3 theme/contours.py     # réécrit theme/static/contours.svg
make static                   # sinon le nouveau fichier n'est pas servi
```

Les courbes sont posées en **masque** CSS, pas en image de fond : une seule
source SVG, teintée par `background-color`, d'où le même fichier en bleu sur la
page claire et en blanc sous le bandeau.

Deux limites à connaître avant de s'approprier le thème :

- le **logo est celui d'OPENGIS.ch**, repris tel quel. Il habille une instance
  QFieldCloud, il ne dit pas qui l'exploite. Le nom, lui, est à vous : une seule
  ligne dans `settings_custom.py`, `INSTANCE_NAME`, le porte partout — onglet,
  admin, page de connexion. La laisser sur `Mon instance QFieldCloud` laisse
  l'instance anonyme, ce qui est un choix, pas un oubli ;
- l'admin ne reçoit **que** les couleurs Jazzmin (`JAZZMIN_UI_TWEAKS`), pas
  `theme.css` : `custom_css` reste celui de l'upstream, qui porte déjà les
  correctifs de l'admin QFieldCloud.

Quatre choses à ne pas oublier :

- le module de réglages se monte sur **`app` et `worker_wrapper`** — ils
  partagent le même bloc d'environnement, et le worker ne démarre pas sans lui ;
- **`make static`** après toute modification de `theme/static/` : le stockage
  statique est à manifeste, et une référence non collectée donne une erreur 500
  sur la page entière, pas une image manquante ;
- **redémarrer `app` après `make static`** quand le *contenu* d'un fichier a
  changé. Le manifeste est lu au démarrage : `collectstatic` écrit bien le
  nouveau nom haché sur le disque, mais le processus continue de servir la page
  avec l'ancien. Rien ne casse, rien ne prévient — la modification semble
  simplement sans effet. `cd src && docker compose --env-file ../.env restart app` ;
- **`make theme-diff`** à chaque montée de version. Sortie vide = le gabarit
  upstream n'a pas bougé. Sortie non vide = reporter la ligne `<link>` dans le
  nouveau gabarit, puis rafraîchir le fichier `.upstream`.

### Revenir au thème de l'upstream

Le thème est livré actif ; ceci le retire et rend à l'instance l'apparence
d'origine de QFieldCloud — le logo upstream, sa palette, aucune courbe. Rien
n'est perdu au passage : `theme/` reste en place, et le chemin se refait dans
l'autre sens.

Le thème tient à **deux** leviers indépendants, et `.env` n'en commande qu'un.
Le module de réglages porte les logos, les titres et les couleurs de l'admin ;
le gabarit `account/base.html`, lui, charge `custom/theme.css` de lui-même, sans
rien demander à Django. Ne défaire que `.env` laisse donc la palette du thème
sur les pages `/accounts/…` — l'instance a l'air inchangée, et c'est normal.

Dans l'ordre :

```shell
# 1. Les réglages : reprendre ceux de l'upstream.
sed -i 's/^DJANGO_SETTINGS_MODULE=.*/DJANGO_SETTINGS_MODULE=qfieldcloud.settings/' .env

# 2. Les montages : commenter le bloc `volumes` du thème sous `app` ET celui
#    sous `worker_wrapper`, dans docker-compose.override.yml.
$EDITOR docker-compose.override.yml

# 3. Recréer les conteneurs, puis recollecter : collectstatic réécrit le
#    manifeste, d'où `custom/` disparaît. C'est l'étape qui purge le thème.
#    Dans cet ordre : `make up` recrée les conteneurs, donc le manifeste que
#    `make static` vient d'écrire est bien celui que le processus a en mémoire.
make up
make static
```

Vérifier plutôt que croire — la sortie attendue est celle-ci, à la lettre :

```shell
cd src && docker compose --env-file ../.env exec app sh -c '
  echo $DJANGO_SETTINGS_MODULE
  grep -c custom/theme.css qfieldcloud/core/templates/account/base.html
  ls qfieldcloud/core/staticfiles/custom 2>&1'
```

```
qfieldcloud.settings
0
ls: cannot access 'qfieldcloud/core/staticfiles/custom': No such file or directory
```

Le retour au thème se fait en défaisant les trois étapes. Décommenter les
montages de `app` et de `worker_wrapper` **ensemble** : sous `settings_custom`,
un worker privé du fichier ne démarre pas.

Un mot sur ce qui est versionné, parce que la moitié de l'opération ne l'est
pas. `docker-compose.override.yml` et `.env.template` sont livrés thème actif ;
votre `.env`, lui, n'est pas dans le dépôt. Une instance qui reprend le template
sans toucher à rien démarre donc thémée, et une instance revenue à l'upstream le
reste tant que son `.env` le dit — mais le prochain `git pull` ne le lui
rappellera pas. C'est le fichier qui décide, pas le dépôt.

## Espacer les tâches planifiées

L'upstream fait frapper Ofelia à la porte de django-cron **toutes les minutes** :

```yaml
ofelia.job-exec.runcrons.schedule: "@every 1m"
```

Chaque passage relance un bootstrap Django complet — import de l'application,
connexion à la base, initialisation de django-axes — soit environ **2,7 s de CPU,
1440 fois par jour**. Sur une instance à quelques utilisateurs et une
synchronisation par jour, c'est du chauffage. Cela s'entend littéralement : sur
l'hyperviseur qui héberge cette instance, ce pic faisait monter le ventilateur
CPU de 2000 à 2400 RPM une fois par minute. La corrélation se lit à la seconde
près entre les `Finished in "2.7...s"` des logs Ofelia et les relevés de
`sensors`.

L'override espace donc la cadence à l'heure :

```yaml
  app:
    labels:
      ofelia.job-exec.runcrons.schedule: "@every 1h"
```

Les labels fusionnent par clé : `enabled`, `command` et `no-overlap` restent ceux
du sous-module, seul `schedule` est remplacé. À vérifier avec `make config`, ou
plutôt `docker compose --env-file ../.env config | grep ofelia`.

**Ofelia ne dégrade aucune tâche, il ne fait que retarder.** Chaque classe de
`CRON_CLASSES` porte sa propre fréquence et django-cron ne l'exécute que si son
délai est écoulé. Le seul effet est donc un retard, borné par la cadence Ofelia :

| Tâche | `run_every_mins` | Conséquence à `@every 1h` |
|---|---|---|
| `qfieldcloud.send_notifications` | 1 | notification retardée jusqu'à 1 h |
| `qfieldcloud.resend_failed_invitations` | 1 | idem |
| `qfieldcloud.set_terminated_workers_to_final_status` | 3 | un job dont le worker est mort reste `STARTED` jusqu'à 1 h |
| `qfieldcloud.delete_obsolete_project_packages` | 60 | voir ci-dessous |

**Ne pas aller au-delà d'une heure.** `delete_obsolete_project_packages` ne balaye
que les projets modifiés dans les **70 dernières minutes**. À `@every 2h`, la
fenêtre ne recouvre plus l'intervalle : les projets modifiés dans le trou ne sont
jamais nettoyés, et leurs packages obsolètes s'accumulent en silence. Le
worker-wrapper en supprime déjà une partie au moment du packaging, mais ce cron
est le filet de sécurité — inutile de le trouer.

Le label vit sur le conteneur `app`, et Ofelia relit les labels au démarrage. Il
faut donc les deux commandes :

```bash
make up
cd src && docker compose --env-file ../.env restart ofelia
docker compose --env-file ../.env logs ofelia | grep "job registered"
```

La dernière ligne doit annoncer `New job registered "runcrons" ... "@every 1h"`.
Un `exit code 137` sur le `runcrons` juste avant le redémarrage est normal :
c'est l'`exec` en cours, tué par la recréation du conteneur `app`.

## Journalisation

L'upstream ne pose de plafond que sur cinq services :

```text
app              1000m × 10 =  9,8 Go
nginx            1000m × 10 =  9,8 Go
qgis3, qgis4, worker_wrapper  100m × 10 =  1,0 Go chacun
                             ────────
                              22,5 Go
```

Ce total, souvent cité, est un **plancher et non un plafond** : `db`, `ofelia`,
`memcached`, `smtp4dev`, `webdav`, `mkcert` et `mirror_transformation_grids` ne
déclarent aucune limite et retombent sur le défaut du démon, `json-file` **sans
limite**. Le service le plus exposé est justement `db`, que le profil standalone
lance avec `log_statement=all`.

L'override borne tous les services que Compose gère, à `100m × 5`, soit **5,9 Go
au total** au lieu d'un plafond non borné :

```yaml
x-logging-cap: &logging-cap
  options:
    max-size: "100m"
    max-file: "5"
```

Les options de journalisation sont figées à la création d'un conteneur : un
`make up` est nécessaire, et `docker inspect <conteneur> --format
'{{.HostConfig.LogConfig.Config}}'` dit ce qui s'applique réellement.

**Un filet reste à poser hors du dépôt.** Les conteneurs QGIS éphémères sont
créés par `worker_wrapper` via l'API Docker, pas par Compose : aucun fichier de
ce dépôt ne les couvre, et ils ne connaissent que le défaut du démon. Sur la
machine :

```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "100m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

Le redémarrage du démon coupe brièvement tous les conteneurs. Ce défaut ne
s'applique qu'aux conteneurs **créés ensuite** : il ne change rien à ceux qui
tournent déjà, dont les options sont figées.

## Sauvegarde

Trois choses, et trois seulement :

- la base — `pg_dump` logique ;
- le bucket du stockage objet — miroir S3 ;
- le `.env`, sans lequel les deux premiers sont inexploitables (`SECRET_KEY` et
  `SALT_KEY` déchiffrent les champs chiffrés de la base).

Les grilles PROJ (~850 Mo) et les images sont intégralement reconstructibles.

Deux ordonnanceurs, pour une raison précise :

| Quoi | Par qui | Quand |
|---|---|---|
| `pg_dump -Fc` + purge à 14 jours | **ofelia**, `job-exec` sur `db` (labels de l'override) | 02:30 |
| miroir du bucket + copie du `.env` | **crontab utilisateur**, `make backup` | 02:45 |

La ligne de crontab, en absolu puisque cron ne se place nulle part :

```cron
45 2 * * * make -C /opt/docker/qfieldcloud-stack backup >> /opt/docker/qfieldcloud-stack/backups/backup-storage.log 2>&1
```

Elle passe par le `Makefile` et jamais par `scripts/backup-storage.sh` :
l'emplacement du script reste ainsi un détail interne. Le déplacer ne casserait
pas une ligne de crontab qui, elle, ne préviendrait personne — elle échouerait à
2 h 45 dans un fichier de log que personne ne lit.

Pourquoi pas ofelia pour les deux : en 0.3.18, un job **`job-run` déclaré par
label n'est jamais enregistré** — aucune erreur, il n'apparaît simplement pas
dans les `New job registered` du journal. Et les labels sont lisibles par
`docker inspect` : la clé secrète du stockage objet n'a rien à y faire.

Les fichiers atterrissent dans `backups/` (ignoré par git), d'où la sauvegarde
du conteneur les emporte hors machine.

### Configurer le miroir du bucket

`scripts/backup-storage.sh` lit quatre variables qui n'existent pas chez l'upstream
et ne servent qu'à lui — l'application, elle, lit `STORAGES` :

| Variable | Valeur |
|---|---|
| `S3_BACKUP_ENDPOINT` | URL de l'API S3 |
| `S3_BACKUP_ACCESS_KEY`, `S3_BACKUP_SECRET_KEY` | Une clé en lecture suffit |
| `S3_BACKUP_BUCKET` | Le `bucket_name` de `STORAGES` |

Rien là-dedans n'est propre à un fournisseur : c'est du `mc mirror` standard. **En
profil standalone** (rustfs embarqué), pointez l'endpoint sur
`${STORAGE_API_BIND_IP}:${OBJECT_STORAGE_API_PORT}` et réutilisez
`OBJECT_STORAGE_ROOT_USER` / `OBJECT_STORAGE_ROOT_PASSWORD`. Le script refuse de
démarrer, en nommant les variables fautives, si l'une manque ou est restée à
`change_me`.

Ces quatre variables figurent dans `IGNORED_VARS` du `Makefile` : `check_envvars.py`
n'analyse que les fichiers Compose et les signalerait comme orphelines.

**Le miroir tourne avec `--remove`** : un objet supprimé en amont disparaît de la
copie au passage suivant. C'est voulu, mais cela suppose que quelque chose garde
un historique de `backups/` — ici la sauvegarde du conteneur. Sans cet historique
derrière, ce miroir ne protège **pas** d'une suppression accidentelle : il la
recopie fidèlement. Retirez `--remove` si vous n'avez rien de tel.

### Tester la restauration

```bash
make restore-test
```

Restaure le dernier dump dans une base jetable, compare les effectifs table par
table avec la production, vérifie que PostGIS est bien là, puis supprime la base.
Une sauvegarde dont on n'a jamais tenté la restauration n'est pas une sauvegarde.
