"""Routes du portail.

Les chemins reprennent ceux de l'application de référence — `/a/<user>/`,
`/settings/<user>/…` — pour que la documentation et les habitudes suivent.
"""

from django.urls import path

from qfieldcloud.portal import views

urlpatterns = [
    # Reprend le nom `index` de l'upstream : `{% url 'index' %}` est appelé
    # par les gabarits de connexion, et `LOGIN_REDIRECT_URL` vaut ce nom-là.
    path("", views.DashboardView.as_view(), name="index"),
    path(
        "projects/public/",
        views.PublicProjectsView.as_view(),
        name="portal_public_projects",
    ),
    path(
        "a/<str:username>/",
        views.UserProfileView.as_view(),
        name="portal_user_profile",
    ),
    path(
        "settings/<str:username>/",
        views.AccountSettingsView.as_view(),
        name="portal_settings_account",
    ),
    path(
        "settings/<str:username>/profile/",
        views.ProfileSettingsView.as_view(),
        name="portal_settings_profile",
    ),
    path(
        "settings/<str:username>/notifications/",
        views.NotificationSettingsView.as_view(),
        name="portal_settings_notifications",
    ),
    path(
        "settings/<str:username>/security/",
        views.SecuritySettingsView.as_view(),
        name="portal_settings_security",
    ),
    path(
        "settings/<str:username>/security/revoke/",
        views.RevokeTokensView.as_view(),
        name="portal_revoke_tokens",
    ),
]
