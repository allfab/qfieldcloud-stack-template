"""Formulaires du portail.

Chacun est un `ModelForm` sur un modèle de l'upstream. Aucune règle métier
n'est réécrite ici : les validateurs vivent sur les champs du modèle, et les
formulaires n'exposent que le sous-ensemble qu'un utilisateur a le droit de
changer lui-même.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from qfieldcloud.core.models import Person, UserAccount


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
