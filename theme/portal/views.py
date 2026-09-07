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
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, UpdateView, View

from qfieldcloud.authentication.models import AuthToken
from qfieldcloud.core.models import Organization, Person, ProjectCollaborator
from qfieldcloud.core.serializers import get_avatar_url
from qfieldcloud.portal.forms import AccountForm, NotificationsForm, ProfileForm
from qfieldcloud.project.enums import ProjectRoleOrigins
from qfieldcloud.project.models import Project

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
            # Le nom d'un projet ne devient un lien que s'il mène quelque part.
            # Tant que le détail projet n'existe pas (lot suivant), seul un
            # membre du staff a une destination : l'admin.
            "can_open_project": self.request.user.is_staff,
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
