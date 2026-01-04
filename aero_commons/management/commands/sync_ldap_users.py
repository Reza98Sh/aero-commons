from django.core.management.base import BaseCommand
from aero_commons.models import CustomUser


class Command(BaseCommand):
    help = "Synchronize users from LDAP"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run without database changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        result = CustomUser.sync_from_ldap(
            dry_run=dry_run,
            callback=lambda msg: self.stdout.write(msg),
        )

        self.stdout.write(self.style.SUCCESS(
            f"Sync completed | Total: {result['total']} | "
            f"Created: {result['created']} | Updated: {result['updated']}"
        ))
