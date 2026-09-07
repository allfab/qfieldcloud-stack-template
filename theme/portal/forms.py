"""Formulaires du portail.

Chacun est un `ModelForm` sur un modèle de l'upstream. Aucune règle métier
n'est réécrite ici : les validateurs vivent sur les champs du modèle, et les
formulaires n'exposent que le sous-ensemble qu'un utilisateur a le droit de
changer lui-même.
"""

from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from qfieldcloud.core.models import (
    Organization,
    OrganizationMember,
    Person,
    ProjectCollaborator,
    Secret,
    UserAccount,
)
from qfieldcloud.project.models import Project


class AccountForm(forms.ModelForm):
    """Identité du compte : ce que les autres voient et par quoi on l'atteint.

    `username` est affiché mais verrouillé — le renommer casse les URL de tous
    ses projets, et l'upstream ne prévoit aucune redirection. `email` est un
    champ ordinaire, mais il n'est PAS enregistré ici : voir la vue, qui le
    confie à allauth pour qu'une confirmation parte à la nouvelle adresse.
    """

    email = forms.EmailField(
        label=_("Adresse e-mail"),
        required=True,
        help_text=_(
            "Changer d'adresse envoie un lien de confirmation à la nouvelle. "
            "L'ancienne reste celle du compte tant que le lien n'est pas suivi."
        ),
    )

    class Meta:
        model = Person
        fields = ("first_name", "last_name")
        labels = {
            "first_name": _("Prénom"),
            "last_name": _("Nom"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].initial = self.instance.email


class ProfileForm(forms.ModelForm):
    """Profil public : l'avatar, la biographie, le fuseau horaire."""

    class Meta:
        model = UserAccount
        fields = (
            "avatar",
            "bio",
            "company",
            "location",
            "timezone",
            "is_email_public",
        )
        labels = {
            "avatar": _("Avatar"),
            "bio": _("Biographie"),
            "company": _("Organisme"),
            "location": _("Localisation"),
            "timezone": _("Fuseau horaire"),
            "is_email_public": _("Rendre l'adresse e-mail publique"),
        }
        help_texts = {
            "avatar": _("L'avatar est affiché publiquement sur le profil."),
        }


class NotificationsForm(forms.ModelForm):
    """Fréquence des courriels de notification.

    Le champ est une `DurationField` à choix fermés côté modèle ; on n'y touche
    pas, on l'affiche.
    """

    class Meta:
        model = UserAccount
        fields = ("notifs_frequency",)
        labels = {
            "notifs_frequency": _("Fréquence des courriels de notification"),
        }


class AddCollaboratorForm(forms.Form):
    """Ajout d'un collaborateur, par nom d'utilisateur ou par adresse e-mail.

    Le formulaire ne valide rien de métier : tout est délégué à
    `projects_utils.create_collaborator_by_username_or_email`, qui applique les
    règles de l'upstream (appartenance à l'organisation, plafond du plan,
    utilisateur déjà collaborateur, invitation d'un inconnu par e-mail) et
    renvoie un message prêt à afficher.
    """

    username = forms.CharField(
        label=_("Nom d'utilisateur ou adresse e-mail"),
        max_length=254,
        widget=forms.TextInput(
            attrs={"placeholder": _("nom-utilisateur ou adresse@exemple.org")}
        ),
    )


class CollaboratorRoleForm(forms.ModelForm):
    """Changement de rôle d'un collaborateur déjà en place."""

    class Meta:
        model = ProjectCollaborator
        fields = ("role",)
        labels = {"role": _("Rôle")}


class OrganizationForm(forms.ModelForm):
    """Création d'une organisation.

    `organization_owner` et `created_by` ne sont pas exposés : c'est la
    personne qui remplit le formulaire, la vue les pose. Le compte, son
    abonnement et son plan par défaut sont créés par `User.save()`, comme pour
    n'importe quel compte.
    """

    class Meta:
        model = Organization
        fields = ("username", "default_project_role_for_members")
        labels = {
            "username": _("Nom de l'organisation"),
            "default_project_role_for_members": _(
                "Rôle par défaut des membres sur les projets"
            ),
        }
        help_texts = {
            "default_project_role_for_members": _(
                "Laisser vide pour n'accorder aucun accès automatique."
            ),
        }


class AddMemberForm(forms.Form):
    """Ajout d'un membre à une organisation, par nom d'utilisateur ou e-mail."""

    member = forms.CharField(
        label=_("Nom d'utilisateur ou adresse e-mail"),
        max_length=254,
        widget=forms.TextInput(
            attrs={"placeholder": _("nom-utilisateur ou adresse@exemple.org")}
        ),
    )
    role = forms.ChoiceField(
        label=_("Rôle"),
        choices=OrganizationMember.Roles.choices,
        initial=OrganizationMember.Roles.MEMBER,
    )


class TeamForm(forms.Form):
    """Création d'une équipe.

    Le nom saisi est le nom court ; l'upstream stocke `@organisation/équipe`
    (voir `Team.format_team_name`), et c'est la vue qui compose. On valide donc
    ici la partie que l'utilisateur écrit, pas la chaîne finale.
    """

    name = forms.CharField(
        label=_("Nom de l'équipe"),
        max_length=100,
        validators=[
            RegexValidator(
                r"^[-a-zA-Z0-9_]+$",
                _("Lettres, chiffres, tirets et soulignés seulement."),
            )
        ],
    )


class AddTeamMemberForm(forms.Form):
    """Ajout d'un membre à une équipe.

    Le modèle refuse déjà quelqu'un qui n'est pas membre de l'organisation
    (`TeamMember.clean`) : rien à revalider ici.
    """

    member = forms.CharField(
        label=_("Nom d'utilisateur ou adresse e-mail"),
        max_length=254,
    )


class OrganizationSettingsForm(forms.ModelForm):
    """Les réglages d'une organisation qui se changent après coup.

    Le nom n'y est pas : il est dans l'adresse de chacun des projets de
    l'organisation, comme le nom d'utilisateur d'une personne. Le propriétaire
    non plus — le transférer engage tout le contenu, et l'admin le fait.
    """

    class Meta:
        model = Organization
        fields = ("default_project_role_for_members",)
        labels = {
            "default_project_role_for_members": _(
                "Rôle par défaut des membres sur les projets"
            ),
        }
        help_texts = {
            "default_project_role_for_members": _(
                "Accordé automatiquement à tout membre non-administrateur sur "
                "tous les projets de l'organisation. Laisser vide pour n'accorder "
                "aucun accès automatique."
            ),
        }


class OrganizationProfileForm(forms.ModelForm):
    """Le profil public d'une organisation.

    Une organisation a un `UserAccount` comme n'importe quel compte. On n'en
    expose que ce qui la décrit — ni fuseau horaire ni visibilité de l'adresse,
    qui ne veulent rien dire pour elle.
    """

    class Meta:
        model = UserAccount
        fields = ("avatar", "bio", "company", "location")
        labels = {
            "avatar": _("Logo"),
            "bio": _("Description"),
            "company": _("Organisme de rattachement"),
            "location": _("Localisation"),
        }


class ProjectSettingsForm(forms.ModelForm):
    """Les réglages d'un projet.

    Aucune contrainte n'est réécrite : `Project.save()` appelle `clean()`, que
    le `full_clean()` du formulaire déclenche aussi — le type de projet hors
    liste et le rôle public hors liste sont donc refusés par l'upstream, pas
    par nous.

    `storage_keep_versions` n'est honoré que si le plan du propriétaire est
    premium (`owner_aware_storage_keep_versions`). La vue le verrouille sinon,
    plutôt que de laisser saisir une valeur sans effet.
    """

    class Meta:
        model = Project
        fields = (
            "name",
            "description",
            "project_type",
            "is_public",
            "public_collaborator_role",
            "overwrite_conflicts",
            "has_restricted_projectfiles",
            "is_attachment_download_on_demand",
            "storage_keep_versions",
            "packaging_offliner",
        )
        labels = {
            "name": _("Nom"),
            "description": _("Description"),
            "project_type": _("Type de projet"),
            "is_public": _("Projet public"),
            "public_collaborator_role": _("Rôle accordé à tous si le projet est public"),
            "overwrite_conflicts": _("Écraser les conflits"),
            "has_restricted_projectfiles": _("Restreindre les fichiers de projet"),
            "is_attachment_download_on_demand": _(
                "Télécharger les pièces jointes à la demande"
            ),
            "storage_keep_versions": _("Versions de fichier à conserver"),
            "packaging_offliner": _("Moteur de packaging"),
        }

    def __init__(self, *args, **kwargs):
        # Le type de projet n'est configurable que sur deux valeurs : la
        # troisième, `shared_datasets`, se pose à la création et l'upstream la
        # refuse ensuite. L'offrir au choix serait offrir une erreur.
        super().__init__(*args, **kwargs)
        self.fields["project_type"].choices = [
            (value, label)
            for value, label in self.fields["project_type"].choices
            if value in Project.CONFIGURABLE_PROJECT_TYPES
        ]


class AddSecretForm(forms.ModelForm):
    """Ajout d'un secret de projet.

    `value` est un `EncryptedTextField` : il est chiffré en base, et l'upstream
    ne prévoit aucune relecture en clair. Un secret s'ajoute et se retire, il ne
    se modifie pas — d'où l'absence de formulaire d'édition.
    """

    class Meta:
        model = Secret
        fields = ("name", "type", "value", "assigned_to")
        labels = {
            "name": _("Nom"),
            "type": _("Type"),
            "value": _("Valeur"),
            "assigned_to": _("Réservé à"),
        }
        help_texts = {
            "assigned_to": _(
                "Laisser vide pour que le secret vaille pour tout le projet. "
                "Sinon, il ne s'applique qu'à ce collaborateur."
            ),
        }
        widgets = {
            "value": forms.PasswordInput(render_value=False),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        # `Secret.clean()` refuse un `assigned_to` qui n'est pas collaborateur
        # du projet ; autant ne proposer que ceux qui le sont.
        if project is not None:
            self.fields["assigned_to"].queryset = Person.objects.for_project(
                project=project, skip_invalid=True
            )
        self.fields["assigned_to"].required = False
