from django.apps import AppConfig


class PortalConfig(AppConfig):
    """Le portail n'a pas de modèle à lui : il ne fait que des pages.

    Tout ce qu'il affiche appartient déjà à `qfieldcloud.core`,
    `qfieldcloud.project` ou `qfieldcloud.subscription`. Pas de modèle, donc
    pas de migration, donc rien à réconcilier quand le sous-module bouge.
    """

    name = "qfieldcloud.portal"
    label = "portal"
    verbose_name = "Portail utilisateur"
