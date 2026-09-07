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
    path(
        "settings/<str:username>/plan/",
        views.PlanView.as_view(),
        name="portal_settings_plan",
    ),
    path(
        "settings/<str:username>/organizations/",
        views.OrganizationsSettingsView.as_view(),
        name="portal_settings_organizations",
    ),
    path(
        "organizations/new/",
        views.CreateOrganizationView.as_view(),
        name="portal_organization_new",
    ),
    # Les organisations vivent sous `/o/`, pas sous `/a/` : un projet peut
    # légitimement s'appeler « members » ou « teams », et `a/<user>/<projet>/`
    # les avalerait. `/a/<organisation>/` redirige ici.
    path(
        "o/<str:organization_name>/",
        views.OrganizationProjectsView.as_view(),
        name="portal_organization",
    ),
    path(
        "o/<str:organization_name>/members/",
        views.OrganizationMembersView.as_view(),
        name="portal_organization_members",
    ),
    path(
        "o/<str:organization_name>/teams/",
        views.OrganizationTeamsView.as_view(),
        name="portal_organization_teams",
    ),
    path(
        "o/<str:organization_name>/settings/",
        views.OrganizationSettingsView.as_view(),
        name="portal_organization_settings",
    ),
    path(
        "o/<str:organization_name>/teams/<str:team_name>/",
        views.OrganizationTeamView.as_view(),
        name="portal_organization_team",
    ),
    path(
        "plans/",
        views.PlansOverviewView.as_view(),
        name="portal_plans_overview",
    ),
    # Le détail d'un projet. Attention : ce chemin OMBRE une route de
    # l'upstream, `a/<username>/<project_name>/`, qui redirigeait vers l'admin
    # — donc vers une page interdite pour un non-staff. C'est le seul endroit,
    # avec `index`, où le portail prend la place d'une route existante.
    path(
        "a/<str:username>/<str:project_name>/",
        views.ProjectOverviewView.as_view(),
        name="portal_project",
    ),
    path(
        "a/<str:username>/<str:project_name>/files/",
        views.ProjectFilesView.as_view(),
        name="portal_project_files",
    ),
    path(
        "a/<str:username>/<str:project_name>/jobs/",
        views.ProjectJobsView.as_view(),
        name="portal_project_jobs",
    ),
    path(
        "a/<str:username>/<str:project_name>/deltas/",
        views.ProjectDeltasView.as_view(),
        name="portal_project_deltas",
    ),
    path(
        "a/<str:username>/<str:project_name>/collaborators/",
        views.ProjectCollaboratorsView.as_view(),
        name="portal_project_collaborators",
    ),
    path(
        "a/<str:username>/<str:project_name>/secrets/",
        views.ProjectSecretsView.as_view(),
        name="portal_project_secrets",
    ),
    path(
        "a/<str:username>/<str:project_name>/settings/",
        views.ProjectSettingsView.as_view(),
        name="portal_project_settings",
    ),
]
