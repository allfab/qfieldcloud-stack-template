"""Surcouche de thème, chargée à la place de qfieldcloud.settings.

Rien n'est modifié dans src/ : on importe les réglages upstream, puis on
n'écrase que ce qui relève de l'apparence.
"""

from qfieldcloud.settings import *  # noqa: F401,F403
from qfieldcloud.settings import JAZZMIN_SETTINGS

# Pages publiques (connexion, inscription, réinitialisation).
WHITELABEL = {
    "site_title": "SIG allfabox",
    "logo_navbar": "custom/logo-navbar.svg",
    "logo_main": "custom/logo-main.svg",
    "logo_alt": "SIG allfabox",
    "favicon": "custom/favicon.svg",
}

# Admin Django, habillé par Jazzmin.
JAZZMIN_SETTINGS = {
    **JAZZMIN_SETTINGS,
    "site_title": "SIG allfabox",
    "site_header": "SIG allfabox",
    "site_brand": "SIG allfabox",
    "site_logo": "custom/logo-navbar.svg",
    "site_icon": "custom/favicon.svg",
    "login_logo": "custom/logo-main.svg",
    "welcome_sign": "Plateforme SIG de terrain",
    "copyright": "allfabox",
}

# Couleurs de l'admin. Jazzmin les applique sans toucher à un seul gabarit.
JAZZMIN_UI_TWEAKS = {
    "navbar": "navbar-dark navbar-success",
    "brand_colour": "navbar-success",
    "accent": "accent-teal",
    "sidebar": "sidebar-dark-success",
    "theme": "default",
    "button_classes": {"primary": "btn-success"},
}
