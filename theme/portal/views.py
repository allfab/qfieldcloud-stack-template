"""Vues du portail utilisateur.

L'upstream expose toute sa mécanique en REST mais ne livre aucune page pour
un utilisateur ordinaire : `/` redirige vers l'admin, et un compte non-staff y
tourne en boucle de redirections. Ces vues comblent ce trou sans rien
réimplémenter — les projets viennent de `Project.objects.for_user()`, qui
porte déjà toutes les règles de visibilité, et le compte reste géré par
allauth.
"""

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, TemplateView, UpdateView, View

from qfieldcloud.authentication.models import AuthToken
from qfieldcloud.core import permissions_utils as perms
from qfieldcloud.core.models import (
    Delta,
    Organization,
    OrganizationMember,
    Person,
    ProjectCollaborator,
    Team,
    TeamMember,
    User,
    UserAccount,
)
from qfieldcloud.core.serializers import get_avatar_url
from qfieldcloud.filestorage.models import File, FileVersion
from qfieldcloud.portal.forms import (
    AccountForm,
    AddCollaboratorForm,
    AddMemberForm,
    AddTeamMemberForm,
    CollaboratorRoleForm,
    NotificationsForm,
    OrganizationForm,
    ProfileForm,
    TeamForm,
)
from qfieldcloud.project.enums import ProjectCollaboratorRole, ProjectRoleOrigins
from qfieldcloud.project.models import Project
from qfieldcloud.project.utils.projects_utils import (
    create_collaborator_by_username_or_email,
)
from qfieldcloud.subscription.exceptions import SubscriptionException
from qfieldcloud.subscription.models import Package, PackageType

# Les tris proposés par l'en-tête du tableau. Une allowlist, pas un
# `order_by(request.GET[...])` : le paramètre vient du navigateur.
SORT_ORDERS = {
    "name": ("owner__username", "name"),
    "-name": ("-owner__username", "-name"),
    "storage": ("file_storage_bytes",),
    "-storage": ("-file_storage_bytes",),
    "updated": ("updated_at",),
    "-updated": ("-updated_at",),
}
DEFAULT_SORT = "-updated"

VISIBILITY_FILTERS = {
    "private": Q(is_public=False),
    "public": Q(is_public=True),
}


class ProjectListMixin:
    """Le tableau de projets, partagé par les trois pages qui l'affichent.

    Une seule source pour la recherche, les filtres et le tri : le tableau se
    comporte pareil sur « Mes projets », sur un profil et sur les projets
    publics.
    """

    #: Si vrai, on retire les projets qui ne sont visibles que parce qu'ils
    #: sont publics — c'est ce que fait l'API sur son endpoint de liste.
    exclude_public_only = True

    def get_project_queryset(self):
        projects = Project.objects.with_prefetch().for_user(self.request.user)

        if self.exclude_public_only:
            projects = projects.exclude(user_role_origin=ProjectRoleOrigins.PUBLIC)

        # Le nombre de collaborateurs passe par une sous-requête, pas par un
        # `Count("collaborators")` : `with_prefetch()` compte déjà les jobs sur
        # une autre jointure, et deux agrégats sur deux jointures se
        # multiplieraient l'un l'autre.
        collaborators = (
            ProjectCollaborator.objects.filter(
                project=OuterRef("pk"),
                is_incognito=False,
            )
            .values("project")
            .annotate(total=Count("id"))
            .values("total")
        )

        return projects.annotate(collaborators_count=Subquery(collaborators))

    def filter_projects(self, projects):
        query = self.request.GET.get("q", "").strip()
        if query:
            projects = projects.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(owner__username__icontains=query)
            )

        visibility = self.request.GET.get("visibility", "")
        if visibility in VISIBILITY_FILTERS:
            projects = projects.filter(VISIBILITY_FILTERS[visibility])

        sort = self.request.GET.get("sort", DEFAULT_SORT)
        if sort not in SORT_ORDERS:
            sort = DEFAULT_SORT

        return projects.order_by(*SORT_ORDERS[sort]), query, visibility, sort

    def get_project_context(self, projects):
        projects, query, visibility, sort = self.filter_projects(projects)

        return {
            "projects": projects,
            "query": query,
            "visibility": visibility,
            "sort": sort,
        }


class AccountSidebarMixin:
    """Colonne de gauche des pages de compte, et le garde-fou qui va avec.

    Les URL portent le nom d'utilisateur — comme sur l'application de
    référence — mais personne ne règle le compte d'un autre : on compare, et
    on renvoie un 404 plutôt qu'un 403, pour ne pas confirmer l'existence du
    compte visé.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        if kwargs.get("username") != request.user.username:
            raise Http404

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["account_user"] = self.request.user
        context["avatar_url"] = get_avatar_url(self.request.user, self.request)
        return context


class DashboardView(LoginRequiredMixin, ProjectListMixin, TemplateView):
    """La page d'accueil d'un utilisateur connecté : ses projets."""

    template_name = "portal/dashboard.html"
    extra_context = {"nav_section": "projects"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        account = user.useraccount

        storage_total_bytes = account.current_subscription.active_storage_total_bytes

        context.update(self.get_project_context(self.get_project_queryset()))
        context.update(
            {
                "profile_user": user,
                "is_own_profile": True,
                "avatar_url": get_avatar_url(user, self.request),
                "organizations": Organization.objects.of_user(user),
                "storage_used_bytes": account.storage_used_bytes,
                "storage_total_bytes": storage_total_bytes,
                "storage_used_ratio": account.storage_used_ratio * 100,
            }
        )
        return context


class UserProfileView(LoginRequiredMixin, ProjectListMixin, TemplateView):
    """Le profil d'un utilisateur, `/a/<username>/`.

    Sur son propre profil, c'est le tableau de bord. Sur celui d'un autre, le
    tableau ne montre que ce que `for_user()` laisse passer.
    """

    template_name = "portal/dashboard.html"
    extra_context = {"nav_section": "projects"}

    def get(self, request, *args, **kwargs):
        # Une organisation possède des projets, donc son nom apparaît partout
        # où un propriétaire est affiché. Sans cette redirection, tous ces
        # liens tomberaient en 404 — une organisation n'est pas une `Person`.
        # Ses pages vivent sous `/o/`, pour ne pas entrer en collision avec
        # `a/<user>/<projet>/` : rien n'interdit d'appeler un projet
        # « members ».
        if Organization.objects.filter(username=kwargs["username"]).exists():
            return redirect(
                "portal_organization", organization_name=kwargs["username"]
            )

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        username = kwargs["username"]
        user = self.request.user

        try:
            profile_user = Person.objects.get(username=username)
        except Person.DoesNotExist:
            raise Http404

        is_own_profile = profile_user == user
        account = profile_user.useraccount

        projects = self.get_project_queryset().filter(owner=profile_user)
        context.update(self.get_project_context(projects))
        context.update(
            {
                "profile_user": profile_user,
                "is_own_profile": is_own_profile,
                "avatar_url": get_avatar_url(profile_user, self.request),
                "organizations": Organization.objects.of_user(profile_user).filter(
                    membership_role_is_public=True
                ),
            }
        )

        # Le quota de stockage ne regarde que son propriétaire.
        if is_own_profile:
            subscription = account.current_subscription
            context.update(
                {
                    "storage_used_bytes": account.storage_used_bytes,
                    "storage_total_bytes": subscription.active_storage_total_bytes,
                    "storage_used_ratio": account.storage_used_ratio * 100,
                }
            )

        return context


class PublicProjectsView(LoginRequiredMixin, ProjectListMixin, TemplateView):
    """Les projets publics de l'instance."""

    template_name = "portal/public_projects.html"
    extra_context = {"nav_section": "public"}
    exclude_public_only = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = self.get_project_queryset().filter(is_public=True)
        context.update(self.get_project_context(projects))
        return context


class AccountSettingsView(LoginRequiredMixin, AccountSidebarMixin, UpdateView):
    """Compte utilisateur : nom, prénom, adresse e-mail."""

    template_name = "portal/settings_account.html"
    extra_context = {"settings_section": "account"}
    form_class = AccountForm

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse(
            "portal_settings_account",
            kwargs={"username": self.request.user.username},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Une adresse en attente signifie qu'un changement a été demandé mais
        # que le lien n'a pas encore été suivi.
        context["pending_email"] = EmailAddress.objects.get_new(self.request.user)
        context["connected_accounts"] = self.request.user.socialaccount_set.all()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        new_email = form.cleaned_data["email"].strip()
        if new_email.lower() != self.request.user.email.lower():
            # On ne touche pas à `User.email` : allauth crée l'adresse, envoie
            # la confirmation, et ne la promeut en adresse du compte qu'une
            # fois le lien suivi. Écrire le champ à la main ferait perdre
            # l'accès au compte si l'adresse était fautive.
            EmailAddress.objects.add_new_email(
                self.request, self.request.user, new_email
            )
            messages.info(
                self.request,
                _(
                    "Un lien de confirmation a été envoyé à %(email)s. "
                    "L'adresse du compte changera une fois le lien suivi."
                )
                % {"email": new_email},
            )

        messages.success(self.request, _("Le compte a été enregistré."))
        return response


class ProfileSettingsView(LoginRequiredMixin, AccountSidebarMixin, UpdateView):
    """Profil public : avatar, biographie, fuseau horaire."""

    template_name = "portal/settings_profile.html"
    extra_context = {"settings_section": "profile"}
    form_class = ProfileForm

    def get_object(self, queryset=None):
        return self.request.user.useraccount

    def get_success_url(self):
        return reverse(
            "portal_settings_profile",
            kwargs={"username": self.request.user.username},
        )

    def form_valid(self, form):
        messages.success(self.request, _("Le profil a été enregistré."))
        return super().form_valid(form)


class NotificationSettingsView(LoginRequiredMixin, AccountSidebarMixin, UpdateView):
    """Fréquence des courriels de notification."""

    template_name = "portal/settings_notifications.html"
    extra_context = {"settings_section": "notifications"}
    form_class = NotificationsForm

    def get_object(self, queryset=None):
        return self.request.user.useraccount

    def get_success_url(self):
        return reverse(
            "portal_settings_notifications",
            kwargs={"username": self.request.user.username},
        )

    def form_valid(self, form):
        messages.success(self.request, _("Les notifications ont été enregistrées."))
        return super().form_valid(form)


class SecuritySettingsView(LoginRequiredMixin, AccountSidebarMixin, PasswordChangeView):
    """Mot de passe et sessions ouvertes sur les autres clients.

    L'upstream bloque `/accounts/password/change/` (« unstyled pages ») ; on
    reprend donc la vue Django, qui invalide bien la session courante et la
    reconduit, avec notre propre gabarit.
    """

    template_name = "portal/settings_security.html"
    extra_context = {"settings_section": "security"}

    def get_success_url(self):
        return reverse(
            "portal_settings_security",
            kwargs={"username": self.request.user.username},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Les connexions par navigateur passent par la session Django, pas par
        # un jeton : les lister ici induirait en erreur.
        context["tokens"] = (
            AuthToken.objects.filter(
                user=self.request.user,
                expires_at__gt=timezone.now(),
            )
            .exclude(client_type=AuthToken.ClientType.BROWSER)
            .order_by("-last_used_at", "-created_at")
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, _("Le mot de passe a été changé."))
        return super().form_valid(form)


class RevokeTokensView(LoginRequiredMixin, AccountSidebarMixin, View):
    """Déconnecte tous les clients : on fait expirer, on ne supprime pas.

    Les jetons sont référencés ailleurs (journaux, statistiques d'usage) ;
    les faire expirer coupe l'accès sans creuser de trous dans l'historique.
    """

    def post(self, request, *args, **kwargs):
        now = timezone.now()
        revoked = (
            AuthToken.objects.filter(
                user=request.user,
                expires_at__gt=now,
            )
            .exclude(client_type=AuthToken.ClientType.BROWSER)
            .update(expires_at=now)
        )

        if revoked:
            messages.success(
                request,
                _("%(count)s client(s) ont été déconnectés.") % {"count": revoked},
            )
        else:
            messages.info(request, _("Aucun client n'était connecté."))

        return HttpResponseRedirect(
            reverse(
                "portal_settings_security",
                kwargs={"username": request.user.username},
            )
        )


# ---------------------------------------------------------------------------
# Détail d'un projet
# ---------------------------------------------------------------------------


class ProjectMixin(LoginRequiredMixin):
    """Le projet, et le droit de voir l'onglet demandé.

    Deux contrôles distincts, dans cet ordre. `for_user(skip_invalid=True)`
    dit si le projet EXISTE pour ce compte — sinon 404, sans confirmer qu'il
    existe pour quelqu'un d'autre. Puis `permission_check` dit si cet onglet-là
    lui est ouvert — sinon 403, puisque l'existence est déjà connue.

    Aucune de ces deux règles n'est écrite ici : ce sont celles de
    `core/permissions_utils.py`, que l'API applique de son côté.
    """

    #: La fonction de `permissions_utils` qui garde cet onglet.
    permission_check = staticmethod(perms.can_retrieve_project)

    #: L'onglet actif, pour le surligner dans la barre du projet.
    project_tab = "overview"

    def get_project(self) -> Project:
        if not hasattr(self, "_project"):
            self._project = get_object_or_404(
                Project.objects.with_prefetch().for_user(
                    self.request.user, skip_invalid=True
                ),
                owner__username=self.kwargs["username"],
                name=self.kwargs["project_name"],
            )

        return self._project

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        if not self.permission_check(request.user, self.get_project()):
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_project()
        user = self.request.user

        context.update(
            {
                "project": project,
                "project_tab": self.project_tab,
                "nav_section": "projects",
                # Les onglets se dessinent d'après les mêmes fonctions que les
                # gardes : un onglet affiché est un onglet accessible.
                "can_read_files": perms.can_read_files(user, project),
                "can_list_jobs": perms.can_list_jobs(user, project),
                "can_read_deltas": perms.can_read_deltas(user, project),
                "can_read_collaborators": perms.can_read_collaborators(user, project),
            }
        )
        return context


class ProjectOverviewView(ProjectMixin, TemplateView):
    """Ce que le projet est : son fichier QGIS, ses couches, son état."""

    template_name = "portal/project_overview.html"
    project_tab = "overview"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_project()

        context.update(
            {
                "qgis_project": getattr(project, "qgis_project", None),
                # Les cinq derniers jobs suffisent à dire si ça tourne rond ;
                # l'onglet Traitements porte l'historique complet.
                "recent_jobs": project.jobs.order_by("-created_at")[:5],
                "collaborators_count": project.direct_collaborators.count(),
            }
        )
        return context


class ProjectFilesView(ProjectMixin, TemplateView):
    """Les fichiers du projet.

    Le téléchargement ne passe pas par une vue à nous : le lien pointe sur
    `filestorage_crud_file`, l'endpoint de l'API. Il accepte la session Django
    (`SessionAuthentication` est dans `DEFAULT_AUTHENTICATION_CLASSES`),
    revérifie `can_read_files`, et sert le fichier par X-Accel-Redirect.
    """

    template_name = "portal/project_files.html"
    project_tab = "files"
    permission_check = staticmethod(perms.can_read_files)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["files"] = (
            self.get_project()
            .project_files.select_related("latest_version", "uploaded_by")
            .order_by("name")
        )
        return context


class ProjectJobsView(ProjectMixin, TemplateView):
    """L'historique des traitements : packaging, deltas, lecture du .qgs."""

    template_name = "portal/project_jobs.html"
    project_tab = "jobs"
    permission_check = staticmethod(perms.can_list_jobs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["jobs"] = (
            self.get_project()
            .jobs.select_related("created_by")
            .order_by("-created_at")[:100]
        )
        return context


class ProjectDeltasView(ProjectMixin, TemplateView):
    """Les modifications remontées du terrain, et ce qu'elles sont devenues."""

    template_name = "portal/project_deltas.html"
    project_tab = "deltas"
    permission_check = staticmethod(perms.can_read_deltas)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        deltas = self.get_project().deltas.select_related("created_by")

        status = self.request.GET.get("status", "")
        if status in Delta.Status.values:
            deltas = deltas.filter(last_status=status)

        context.update(
            {
                "deltas": deltas.order_by("-created_at")[:200],
                "status": status,
                "statuses": Delta.Status.choices,
            }
        )
        return context


class ProjectCollaboratorsView(ProjectMixin, TemplateView):
    """Qui travaille sur le projet, et à quel titre.

    L'ajout passe par `projects_utils.create_collaborator_by_username_or_email`,
    écrit par l'upstream pour exactement cet usage et appelé nulle part dans le
    dépôt open source. Il porte les règles qu'un formulaire n'a pas à
    réécrire — plafond du plan, appartenance à l'organisation, invitation d'un
    inconnu par e-mail — et rend un message déjà traduit.
    """

    template_name = "portal/project_collaborators.html"
    project_tab = "collaborators"
    permission_check = staticmethod(perms.can_read_collaborators)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_project()
        user = self.request.user

        context.update(
            {
                "collaborators": project.collaborators.select_related(
                    "collaborator"
                ).order_by("collaborator__username"),
                "add_form": kwargs.get("add_form") or AddCollaboratorForm(),
                "roles": ProjectCollaboratorRole.choices,
                "can_create_collaborators": perms.can_create_collaborators(
                    user, project
                ),
                "can_update_collaborators": perms.can_update_collaborators(
                    user, project
                ),
                "can_delete_collaborators": perms.can_delete_collaborators(
                    user, project
                ),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        action = request.POST.get("action", "add")

        if action == "add":
            return self.add_collaborator(request, project)
        if action == "update":
            return self.update_collaborator(request, project)
        if action == "remove":
            return self.remove_collaborator(request, project)

        raise PermissionDenied

    def add_collaborator(self, request, project):
        if not perms.can_create_collaborators(request.user, project):
            raise PermissionDenied

        form = AddCollaboratorForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(add_form=form))

        success, message = create_collaborator_by_username_or_email(
            project, form.cleaned_data["username"], request.user
        )
        # Le message vient de l'upstream et dit précisément ce qui a bloqué :
        # on le rend tel quel plutôt que de le remplacer par un « échec ».
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)

        return HttpResponseRedirect(self.get_tab_url(project))

    def update_collaborator(self, request, project):
        if not perms.can_update_collaborators(request.user, project):
            raise PermissionDenied

        collaborator = get_object_or_404(
            ProjectCollaborator,
            project=project,
            collaborator__username=request.POST.get("username", ""),
        )
        form = CollaboratorRoleForm(request.POST, instance=collaborator)
        if form.is_valid():
            form.instance.updated_by = request.user
            form.save()
            messages.success(
                request,
                _('Le rôle de « %(username)s » a été changé.')
                % {"username": collaborator.collaborator.username},
            )
        else:
            messages.error(request, _("Ce rôle n'existe pas."))

        return HttpResponseRedirect(self.get_tab_url(project))

    def remove_collaborator(self, request, project):
        if not perms.can_delete_collaborators(request.user, project):
            raise PermissionDenied

        collaborator = get_object_or_404(
            ProjectCollaborator,
            project=project,
            collaborator__username=request.POST.get("username", ""),
        )
        username = collaborator.collaborator.username
        collaborator.delete()
        messages.success(
            request,
            _('« %(username)s » ne collabore plus à ce projet.')
            % {"username": username},
        )

        return HttpResponseRedirect(self.get_tab_url(project))

    def get_tab_url(self, project) -> str:
        return reverse(
            "portal_project_collaborators",
            kwargs={
                "username": project.owner.username,
                "project_name": project.name,
            },
        )


class PlanView(LoginRequiredMixin, AccountSidebarMixin, TemplateView):
    """« Mon plan » : ce qu'il donne, ce qu'il en reste, ce qu'il refuse.

    Ce n'est pas la page de facturation de l'offre hébergée, et ce n'en est pas
    un ersatz : sur une instance auto-hébergée il n'y a rien à facturer. Ce qui
    manquait, c'est qu'un utilisateur dont le packaging échoue sur
    `PlanInsufficientError` n'avait aucune page pour comprendre pourquoi.
    """

    template_name = "portal/settings_plan.html"
    extra_context = {"settings_section": "plan"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.request.user.useraccount
        subscription = account.current_subscription

        context.update(
            {
                "subscription": subscription,
                "plan": subscription.plan,
                "storage_used_bytes": account.storage_used_bytes,
                "storage_total_bytes": subscription.active_storage_total_bytes,
                "storage_used_ratio": account.storage_used_ratio * 100,
                "projects_count": self.request.user.projects.count(),
            }
        )
        return context


# ---------------------------------------------------------------------------
# Organisations, membres, équipes
# ---------------------------------------------------------------------------


class OrganizationMixin(LoginRequiredMixin):
    """L'organisation, et le droit d'en voir l'onglet demandé.

    Même partage qu'ailleurs : les fonctions de `core/permissions_utils.py`
    gardent, et ce sont elles qui décident aussi de l'affichage de l'onglet.
    `can_read_members` de l'upstream est ouverte à tout compte connecté — c'est
    sa décision, pas la nôtre ; l'écriture, elle, demande le rôle ADMIN.
    """

    permission_check = staticmethod(perms.can_read_members)
    organization_tab = "projects"

    def get_organization(self) -> Organization:
        if not hasattr(self, "_organization"):
            self._organization = get_object_or_404(
                Organization, username=self.kwargs["organization_name"]
            )

        return self._organization

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        if not self.permission_check(request.user, self.get_organization()):
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.get_organization()
        user = self.request.user

        context.update(
            {
                "organization": organization,
                "organization_tab": self.organization_tab,
                "nav_section": "projects",
                "avatar_url": get_avatar_url(organization, self.request),
                "is_organization_admin": perms.can_create_members(user, organization),
            }
        )
        return context


class OrganizationProjectsView(OrganizationMixin, ProjectListMixin, TemplateView):
    """Les projets que l'organisation possède."""

    template_name = "portal/organization_projects.html"
    organization_tab = "projects"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = self.get_project_queryset().filter(owner=self.get_organization())
        context.update(self.get_project_context(projects))
        return context


class OrganizationMembersView(OrganizationMixin, TemplateView):
    """Qui appartient à l'organisation, et à quel titre.

    Le modèle porte les règles : `OrganizationMember.save()` appelle
    `full_clean()`, qui refuse le propriétaire et applique le plafond de
    membres du plan. Sa suppression, elle, retire au passage les
    collaborations de projet et les appartenances d'équipe — ce n'est donc pas
    une simple ligne qui part.
    """

    template_name = "portal/organization_members.html"
    organization_tab = "members"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.get_organization()
        subscription = organization.useraccount.current_subscription

        context.update(
            {
                "members": organization.members.select_related("member").order_by(
                    "member__username"
                ),
                "add_form": kwargs.get("add_form") or AddMemberForm(),
                "roles": OrganizationMember.Roles.choices,
                "members_count": subscription.organization_members_count,
                "max_members": subscription.max_allowed_organization_members,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        organization = self.get_organization()
        action = request.POST.get("action", "add")

        if action == "add":
            return self.add_member(request, organization)
        if action == "update":
            return self.update_member(request, organization)
        if action == "remove":
            return self.remove_member(request, organization)

        raise PermissionDenied

    def add_member(self, request, organization):
        if not perms.can_create_members(request.user, organization):
            raise PermissionDenied

        form = AddMemberForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(add_form=form))

        needle = form.cleaned_data["member"]
        try:
            person = Person.objects.fast_search(needle)
        except Person.DoesNotExist:
            messages.error(
                request,
                _('Aucun compte ne correspond à « %(needle)s ».') % {"needle": needle},
            )
            return HttpResponseRedirect(self.get_tab_url(organization))

        if not perms.can_become_member(person, organization):
            messages.error(
                request,
                _(
                    "« %(username)s » est déjà membre de cette organisation, ou en est "
                    "le propriétaire."
                )
                % {"username": person.username},
            )
            return HttpResponseRedirect(self.get_tab_url(organization))

        try:
            OrganizationMember.objects.create(
                organization=organization,
                member=person,
                role=form.cleaned_data["role"],
                created_by=request.user,
                updated_by=request.user,
            )
        except (ValidationError, SubscriptionException) as error:
            # `ReachedMaxOrganizationMembersError` n'est PAS une
            # `ValidationError` : c'est une `QFieldCloudException`, levée depuis
            # `clean()` et donc pas convertie par `full_clean()`. Sans ce second
            # type dans la capture, le plafond de membres sortirait en 500.
            messages.error(request, self.error_message(error))
        else:
            messages.success(
                request,
                _('« %(username)s » a rejoint l\'organisation.')
                % {"username": person.username},
            )

        return HttpResponseRedirect(self.get_tab_url(organization))

    def update_member(self, request, organization):
        if not perms.can_update_members(request.user, organization):
            raise PermissionDenied

        member = get_object_or_404(
            OrganizationMember,
            organization=organization,
            member__username=request.POST.get("username", ""),
        )
        role = request.POST.get("role", "")
        if role not in OrganizationMember.Roles.values:
            messages.error(request, _("Ce rôle n'existe pas."))
            return HttpResponseRedirect(self.get_tab_url(organization))

        member.role = role
        member.updated_by = request.user
        try:
            member.save()
        except (ValidationError, SubscriptionException) as error:
            messages.error(request, self.error_message(error))
        else:
            messages.success(
                request,
                _('Le rôle de « %(username)s » a été changé.')
                % {"username": member.member.username},
            )

        return HttpResponseRedirect(self.get_tab_url(organization))

    def remove_member(self, request, organization):
        if not perms.can_delete_members(request.user, organization):
            raise PermissionDenied

        member = get_object_or_404(
            OrganizationMember,
            organization=organization,
            member__username=request.POST.get("username", ""),
        )
        username = member.member.username
        member.delete()
        messages.success(
            request,
            _(
                "« %(username)s » a quitté l'organisation. Ses collaborations sur les "
                "projets de l'organisation et ses appartenances d'équipe ont été "
                "retirées avec lui."
            )
            % {"username": username},
        )

        return HttpResponseRedirect(self.get_tab_url(organization))

    @staticmethod
    def error_message(error) -> str:
        """Le message d'une erreur de modèle ou d'abonnement, tel quel."""
        if isinstance(error, ValidationError):
            return " ".join(error.messages)

        return str(getattr(error, "message", error))

    def get_tab_url(self, organization) -> str:
        return reverse(
            "portal_organization_members",
            kwargs={"organization_name": organization.username},
        )


class OrganizationTeamsView(OrganizationMixin, TemplateView):
    """Les équipes de l'organisation.

    Une équipe est un `User` de type TEAM dont le nom d'utilisateur vaut
    `@organisation/équipe` — voir `Team.format_team_name`. On ne stocke que ce
    format-là, et on n'affiche que la partie courte.
    """

    template_name = "portal/organization_teams.html"
    organization_tab = "teams"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.get_organization()

        context.update(
            {
                "teams": Team.objects.filter(
                    team_organization=organization
                ).order_by("username"),
                "team_form": kwargs.get("team_form") or TeamForm(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        organization = self.get_organization()
        action = request.POST.get("action", "add")

        if action == "add":
            return self.add_team(request, organization)
        if action == "remove":
            return self.remove_team(request, organization)

        raise PermissionDenied

    def add_team(self, request, organization):
        if not perms.can_create_members(request.user, organization):
            raise PermissionDenied

        form = TeamForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(team_form=form))

        username = Team.format_team_name(
            organization.username, form.cleaned_data["name"]
        )
        if Team.objects.filter(username=username).exists():
            messages.error(request, _("Une équipe porte déjà ce nom."))
        else:
            Team.objects.create(username=username, team_organization=organization)
            messages.success(
                request,
                _('L\'équipe « %(name)s » a été créée.')
                % {"name": form.cleaned_data["name"]},
            )

        return HttpResponseRedirect(self.get_tab_url(organization))

    def remove_team(self, request, organization):
        if not perms.can_delete_members(request.user, organization):
            raise PermissionDenied

        team = get_object_or_404(
            Team,
            team_organization=organization,
            username=request.POST.get("username", ""),
        )
        name = team.teamname
        team.delete()
        messages.success(
            request, _('L\'équipe « %(name)s » a été supprimée.') % {"name": name}
        )

        return HttpResponseRedirect(self.get_tab_url(organization))

    def get_tab_url(self, organization) -> str:
        return reverse(
            "portal_organization_teams",
            kwargs={"organization_name": organization.username},
        )


class OrganizationTeamView(OrganizationMixin, TemplateView):
    """Les membres d'une équipe.

    `TeamMember.save()` appelle `full_clean()`, qui refuse quelqu'un qui n'est
    pas membre de l'organisation. On laisse donc le modèle trancher et on rend
    son message.
    """

    template_name = "portal/organization_team.html"
    organization_tab = "teams"

    def get_team(self) -> Team:
        if not hasattr(self, "_team"):
            self._team = get_object_or_404(
                Team,
                team_organization=self.get_organization(),
                username=Team.format_team_name(
                    self.kwargs["organization_name"], self.kwargs["team_name"]
                ),
            )

        return self._team

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team = self.get_team()

        context.update(
            {
                "team": team,
                "team_members": TeamMember.objects.filter(team=team)
                .select_related("member")
                .order_by("member__username"),
                "add_form": kwargs.get("add_form") or AddTeamMemberForm(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        organization = self.get_organization()
        team = self.get_team()
        action = request.POST.get("action", "add")

        if action == "add":
            if not perms.can_create_members(request.user, organization):
                raise PermissionDenied

            form = AddTeamMemberForm(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(add_form=form))

            needle = form.cleaned_data["member"]
            try:
                person = Person.objects.fast_search(needle)
            except Person.DoesNotExist:
                messages.error(
                    request,
                    _('Aucun compte ne correspond à « %(needle)s ».')
                    % {"needle": needle},
                )
            else:
                try:
                    TeamMember.objects.create(team=team, member=person)
                except ValidationError as error:
                    messages.error(request, " ".join(error.messages))
                else:
                    messages.success(
                        request,
                        _('« %(username)s » a rejoint l\'équipe.')
                        % {"username": person.username},
                    )

        elif action == "remove":
            if not perms.can_delete_members(request.user, organization):
                raise PermissionDenied

            member = get_object_or_404(
                TeamMember, team=team, member__username=request.POST.get("username", "")
            )
            username = member.member.username
            member.delete()
            messages.success(
                request,
                _('« %(username)s » a quitté l\'équipe.') % {"username": username},
            )

        else:
            raise PermissionDenied

        return HttpResponseRedirect(
            reverse(
                "portal_organization_team",
                kwargs={
                    "organization_name": self.get_organization().username,
                    "team_name": team.teamname,
                },
            )
        )


class OrganizationsSettingsView(LoginRequiredMixin, AccountSidebarMixin, TemplateView):
    """« Mes organisations » : celles qu'on possède, celles où l'on est membre."""

    template_name = "portal/settings_organizations.html"
    extra_context = {"settings_section": "organizations"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["organizations"] = Organization.objects.of_user(self.request.user)
        return context


class CreateOrganizationView(LoginRequiredMixin, CreateView):
    """Créer une organisation.

    `User.save()` se charge du compte, de l'abonnement et du plan par défaut :
    il n'y a rien à faire de plus que poser le propriétaire.
    """

    template_name = "portal/organization_new.html"
    form_class = OrganizationForm
    extra_context = {"nav_section": "projects"}

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not perms.can_create_organizations(
            request.user
        ):
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.organization_owner = self.request.user
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            _('L\'organisation « %(name)s » a été créée.')
            % {"name": form.instance.username},
        )
        return response

    def get_success_url(self):
        return reverse(
            "portal_organization",
            kwargs={"organization_name": self.object.username},
        )


# ---------------------------------------------------------------------------
# Côté exploitant
# ---------------------------------------------------------------------------


class PlansOverviewView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """« Plans et quotas » : la vue d'ensemble que l'admin ne donne pas.

    L'admin fait déjà bien l'ÉCRITURE — changer de plan, ajouter du stockage,
    filtrer, chercher. Ce qu'il ne fait pas, c'est montrer la consommation face
    au quota sur tous les comptes à la fois : la preuve est dans
    `core/admin.py`, où `PersonAdmin.list_display` porte `storage_usage__field`
    en commentaire, parce qu'un agrégat par ligne coûte cher.

    D'où le seul point technique de cette page : le stockage consommé est
    calculé en UNE requête groupée pour tous les comptes, pas en une par
    compte. C'est ce qui la rend tenable là où l'admin a renoncé.

    Le garde n'est pas `is_staff` mais la permission Django qui gouverne déjà
    la lecture des abonnements : elle respecte les groupes, et un superuser
    l'a d'office.
    """

    template_name = "portal/plans_overview.html"
    permission_required = "subscription.view_subscription"
    extra_context = {"nav_section": "plans"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # On part de `UserAccount`, pas de `User`, pour deux raisons.
        #
        # La bonne : un plan et un quota appartiennent au compte, pas à la
        # personne. La contraignante : `User.objects.get_queryset()` appelle
        # `select_subclasses()`, qui reconstruit chaque ligne en Person ou en
        # Organization — l'instance rendue n'est plus celle sur laquelle le
        # `select_related` a été résolu, et son cache est perdu. Le
        # `select_related` est bien émis, mais tout est refait ligne par ligne.
        # `UserAccount.objects` n'a pas cette mécanique.
        #
        # L'abonnement courant vient de la vue SQL `current_subscriptions_vw`.
        # Passer par `useraccount.current_subscription` coûterait deux
        # requêtes de plus par compte — et c'est un `get_or_create`, donc une
        # écriture possible sur une page qui ne fait que lire.
        accounts = (
            UserAccount.objects.filter(
                user__type__in=(User.Type.PERSON, User.Type.ORGANIZATION),
            )
            .select_related(
                "user",
                "current_subscription_vw",
                "current_subscription_vw__plan",
            )
            .order_by("user__username")
        )

        # Le stockage consommé de TOUS les comptes, en une requête.
        used_by_owner = dict(
            FileVersion.objects.filter(
                file__file_type=File.FileType.PROJECT_FILE,
            )
            .values_list("file__project__owner_id")
            .annotate(total=Sum("size"))
        )

        # Le nombre de projets, en une autre. Deux agrégats sur deux jointures
        # ne peuvent pas cohabiter dans la même requête sans se multiplier.
        projects_by_owner = dict(
            Project.objects.values_list("owner_id").annotate(total=Count("id"))
        )

        # Le stockage additionnel acheté, en une troisième. Sur une instance
        # auto-hébergée il n'y en a jamais — mais s'il y en avait, l'omettre
        # afficherait un quota plus bas que celui que l'utilisateur voit sur
        # sa propre page « Mon plan ».
        storage_package_type = PackageType.get_storage_package_type()
        extra_by_account = dict(
            Package.objects.active()
            .filter(type=storage_package_type)
            .values_list("subscription__account_id")
            .annotate(total=Sum("quantity"))
        )
        package_unit_bytes = (
            storage_package_type.unit_amount * 1000 * 1000
            if storage_package_type
            else 0
        )

        rows = []
        for account in accounts:
            user = account.user
            subscription = getattr(account, "current_subscription_vw", None)
            if subscription is None:
                # Un compte sans ligne dans la vue n'a pas d'abonnement
                # courant : on le montre quand même, c'est justement une
                # anomalie que l'exploitant doit voir.
                rows.append(
                    {
                        "account": user,
                        "is_organization": user.is_organization,
                        "plan": None,
                        "subscription": None,
                        "used_bytes": used_by_owner.get(user.pk, 0),
                        "total_bytes": 0,
                        "ratio": 100,
                        "projects_count": projects_by_owner.get(user.pk, 0),
                    }
                )
                continue

            used = used_by_owner.get(user.pk, 0)
            total = subscription.included_storage_bytes + (
                extra_by_account.get(user.pk, 0) * package_unit_bytes
            )
            rows.append(
                {
                    "account": user,
                    "is_organization": user.is_organization,
                    "plan": subscription.plan,
                    "subscription": subscription,
                    "used_bytes": used,
                    "total_bytes": total,
                    "ratio": (used / total * 100) if total else 100,
                    "projects_count": projects_by_owner.get(user.pk, 0),
                }
            )

        sort = self.request.GET.get("sort", "ratio")
        if sort == "name":
            rows.sort(key=lambda row: row["account"].username)
        elif sort == "storage":
            rows.sort(key=lambda row: row["used_bytes"], reverse=True)
        else:
            sort = "ratio"
            rows.sort(key=lambda row: row["ratio"], reverse=True)

        context.update({"rows": rows, "sort": sort})
        return context
