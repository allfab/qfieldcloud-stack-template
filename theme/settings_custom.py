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
