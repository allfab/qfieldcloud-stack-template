"""Aligne les plans de la base sur ceux déclarés dans les réglages.

Les plans `community` et `organization` viennent d'une migration de l'upstream
(`subscription/0002_populate_plans`), qui ne les crée que s'ils n'existent pas.
Une instance neuve hérite donc toujours des valeurs d'OPENGIS.ch — pensées pour
une offre hébergée, pas pour un déploiement à quelques comptes.

Les retoucher à la main dans l'admin marche, mais ne se rejoue pas : le jour où
vous remontez l'instance ailleurs, vous repartez des valeurs upstream sans que
rien ne vous le rappelle. Cette commande fait des quotas une VALEUR VERSIONNÉE,
lue dans `INSTANCE_PLANS` (voir `theme/settings_custom.py`), applicable après
chaque `migrate`.

Elle ne crée aucun plan : ceux-là appartiennent à l'upstream. Elle n'écrit que
les champs déclarés, laisse les autres tels quels, et n'écrit rien si rien ne
change.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from qfieldcloud.subscription.models import Plan


class Command(BaseCommand):
    help = "Aligne les plans existants sur INSTANCE_PLANS, sans en créer aucun."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Montre ce qui changerait, sans rien écrire.",
        )

    def handle(self, *args, **options):
        wanted = getattr(settings, "INSTANCE_PLANS", None)
        if not wanted:
            raise CommandError(
                "INSTANCE_PLANS n'est pas déclaré. Vérifiez que "
                "DJANGO_SETTINGS_MODULE pointe sur votre module de réglages."
            )

        dry_run = options["dry_run"]
        changes = 0

        for code, fields in wanted.items():
            try:
                plan = Plan.objects.get(code=code)
            except Plan.DoesNotExist:
                # Un plan absent n'est pas une erreur : l'instance peut tourner
                # sur un jeu de plans différent. On le signale et on continue.
                self.stdout.write(
                    self.style.WARNING(f"{code} : absent de la base, ignoré")
                )
                continue

            updated = []
            for field, value in fields.items():
                before = getattr(plan, field)
                if before == value:
                    continue

                self.stdout.write(f"{code:14} {field:32} {before!s:>12}  ->  {value}")
                setattr(plan, field, value)
                updated.append(field)

            if not updated:
                self.stdout.write(f"{code:14} déjà aligné")
                continue

            changes += len(updated)
            if not dry_run:
                # `Plan.save()` appelle `full_clean()` : un quota incohérent
                # (seuils d'alerte, notamment) est refusé ici plutôt que
                # d'atterrir en base.
                plan.save(update_fields=updated)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\n{changes} changement(s), rien écrit (--dry-run)")
            )
        elif changes:
            self.stdout.write(self.style.SUCCESS(f"\n{changes} champ(s) mis à jour"))
        else:
            self.stdout.write(self.style.SUCCESS("\nRien à faire, tout est aligné"))
