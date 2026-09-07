"""Surcouche de thème, chargée à la place de qfieldcloud.settings.

Rien n'est modifié dans src/ : on importe les réglages upstream, puis on
n'écrase que ce qui relève de l'apparence.

L'habillage reprend les codes de qfield.cloud — le logo officiel, le bleu de la
marque, le vert de QField, les courbes de niveau — mais l'instance, elle, reste
la vôtre : elle n'appartient pas à OPENGIS.ch et ne doit pas prétendre l'être.
D'où le nom ci-dessous, à changer avant la mise en service.
"""

from qfieldcloud.settings import *  # noqa: F401,F403
from qfieldcloud.settings import INSTALLED_APPS, JAZZMIN_SETTINGS

# La seule ligne à changer : elle nomme l'instance partout, onglet compris.
INSTANCE_NAME = "Mon instance QFieldCloud"

# --- Portail utilisateur -------------------------------------------------
#
# L'upstream ne livre aucune page pour un utilisateur ordinaire : `/` renvoie
# vers l'admin, où un compte non-staff tourne en boucle de redirections. Le
# portail comble ce trou depuis le dehors, comme le thème — une application
# Django montée dans l'image, et une URLconf qui reprend celle de l'upstream.
#
# `django_cleanup` doit rester la DERNIÈRE application installée : elle
# s'accroche aux signaux de suppression de fichiers et veut passer après tout
# le monde. D'où l'insertion en avant-dernière position.
INSTALLED_APPS = [*INSTALLED_APPS[:-1], "qfieldcloud.portal", INSTALLED_APPS[-1]]

ROOT_URLCONF = "qfieldcloud.urls_custom"

# Capacité totale du stockage objet, en octets, ou None si vous ne la déclarez
# pas. Elle est DÉCLARÉE, pas mesurée : les fichiers de projet vivent dans un
# bucket S3 que Django n'a aucun moyen d'interroger sur son espace libre — cela
# relève de la supervision de l'hôte, pas d'une vue web.
#
# Ce que ce chiffre sert : la page « Plans et quotas » compare ce qui est
# CONSOMMÉ, ce qui est PROMIS (la somme des quotas accordés à tous les comptes)
# et ce qui est déclaré ici. Promettre 10 Go à vingt comptes, c'est promettre
# 200 Go — et rien ne vous le disait avant que le bucket ne soit plein.
#
# La valeur livrée est un PLACEHOLDER, comme INSTANCE_NAME : elle sert à ce que
# la page montre à quoi elle ressemble dès le premier démarrage. Mettez la
# vôtre, ou None pour que la page dise simplement qu'elle ne sait pas.
INSTANCE_STORAGE_CAPACITY_BYTES = 50 * 1000**3  # 50 Go

# Quotas des plans, appliqués par `make plans`.
#
# `community` et `organization` viennent d'une migration de l'upstream, qui ne
# les crée que s'ils n'existent pas : une instance neuve hérite donc toujours
# des valeurs d'OPENGIS.ch, taillées pour une offre hébergée. Les retoucher
# dans l'admin marche, mais ne se rejoue pas — remontez l'instance ailleurs et
# vous repartez des valeurs upstream. D'où ce dictionnaire, versionné avec le
# reste, et `make plans` après chaque `migrate`.
#
# Ce qui MORD vraiment, vérifié dans le code de l'upstream :
#   storage_mb                 quota dur, appliqué au packaging et à l'envoi
#   storage_keep_versions      le multiplicateur silencieux : dix versions d'un
#                              paquet de 500 Mo, ce sont 5 Go. C'est le levier
#                              le plus efficace sur la consommation réelle
#   is_external_db_supported   refuse au packaging tout projet branché sur
#                              PostGIS ou un WFS (`PlanInsufficientError`)
#   max_organization_members   plafond appliqué à l'ajout d'un membre
#   is_premium                 débloque les collaborateurs sur un projet privé
#                              appartenant à une PERSONNE, la surcharge de
#                              storage_keep_versions par projet, et les paquets
#                              de stockage additionnel
#
# Ce qui ne mord PAS, malgré son nom : `job_minutes` et
# `synchronizations_per_months` ne sont lus nulle part dans le code. Les régler
# ne limite rien.
#
# Les valeurs ci-dessous sont serrées à dessein : une instance auto-hébergée à
# quelques comptes n'a pas les 10 Go par personne d'une offre commerciale.
# Élargir est une décision d'exploitant, et la page « Plans et quotas » vous
# dira si vos promesses tiennent dans votre stockage réel.
#
# Piège de nommage : `storage_threshold_warning_bytes` et `..._critical_bytes`
# sont des octets RESTANTS, pas des pourcentages. « 400 Mo » veut dire « alerte
# quand il reste 400 Mo », et l'upstream refuse un seuil supérieur ou égal au
# quota. Réduire `storage_mb` sans les réduire fait donc échouer la commande —
# c'est voulu, `Plan.save()` appelle `full_clean()`.
INSTANCE_PLANS = {
    "community": {
        "storage_mb": 2_000,
        "storage_threshold_warning_bytes": 400_000_000,
        "storage_threshold_critical_bytes": 150_000_000,
        "storage_keep_versions": 3,
        # L'upstream le laisse à False, et on le suit : autoriser PostGIS pour
        # un compte personnel suppose que les conteneurs QGIS éphémères
        # atteignent cette base — une décision d'infrastructure, pas un défaut
        # de plan.
        "is_external_db_supported": False,
        "is_premium": True,
    },
    "organization": {
        "storage_mb": 10_000,
        "storage_threshold_warning_bytes": 1_000_000_000,
        "storage_threshold_critical_bytes": 400_000_000,
        "storage_keep_versions": 5,
        "is_external_db_supported": True,
        "is_premium": True,
        "max_organization_members": 25,
    },
}

# Pages publiques (connexion, inscription, réinitialisation).
WHITELABEL = {
    "site_title": INSTANCE_NAME,
    "logo_navbar": "custom/logo-navbar.svg",
    "logo_main": "custom/logo-main.svg",
    "logo_alt": INSTANCE_NAME,
    "favicon": "custom/favicon.svg",
}

# Admin Django, habillé par Jazzmin.
#
# `custom_css` reste celui de l'upstream : il porte déjà les correctifs de
# l'admin QFieldCloud, et l'écraser en ferait hériter la dette.
JAZZMIN_SETTINGS = {
    **JAZZMIN_SETTINGS,
    "site_title": INSTANCE_NAME,
    "site_header": INSTANCE_NAME,
    "site_brand": INSTANCE_NAME,
    "site_logo": "custom/logo-navbar.svg",
    "site_icon": "custom/favicon.svg",
    "login_logo": "custom/logo-main.svg",
    "welcome_sign": "Plateforme SIG de terrain",
    "copyright": INSTANCE_NAME,
}

# Couleurs de l'admin. Jazzmin les applique sans toucher à un seul gabarit.
# `navy` est ce que la palette AdminLTE offre de plus proche du bleu de la
# marque (#4a6fae) ; `olive` tient le rôle du vert de QField en accent.
JAZZMIN_UI_TWEAKS = {
    "navbar": "navbar-dark navbar-navy",
    "brand_colour": "navbar-navy",
    "accent": "accent-olive",
    "sidebar": "sidebar-dark-navy",
    "theme": "default",
    "button_classes": {"primary": "btn-primary"},
}
