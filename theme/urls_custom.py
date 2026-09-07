"""URLconf de l'instance, chargée à la place de `qfieldcloud.urls`.

Rien n'est modifié dans `src/` : on reprend les routes de l'upstream telles
quelles, on écarte la seule qui empêche un portail d'exister, et on met
celles du portail devant.

Cette route écartée est `index` : un `RedirectView` vers l'admin. C'est elle
qui met un compte non-staff en boucle de redirections à la connexion, puisque
`LOGIN_REDIRECT_URL` vaut « index » et que l'admin refuse un non-staff en le
renvoyant à la page de connexion. Le portail reprend le nom, donc tous les
`{% url 'index' %}` de l'upstream continuent de résoudre.
"""

from django.urls import include, path

from qfieldcloud.urls import urlpatterns as upstream_urlpatterns

urlpatterns = [
    path("", include("qfieldcloud.portal.urls")),
    *(
        route
        for route in upstream_urlpatterns
        if getattr(route, "name", None) != "index"
    ),
]
