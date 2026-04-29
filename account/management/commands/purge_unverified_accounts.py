from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from account.models import Account


class Command(BaseCommand):
    help = "Delete accounts with email_verified=False older than 7 days."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Report what would be deleted, but don't delete.",
        )

    def handle(self, *args, dry_run=False, **opts):
        cutoff = timezone.now() - timedelta(days=7)
        qs = Account.objects.filter(email_verified=False, date_joined__lt=cutoff)
        count = qs.count()
        if dry_run:
            self.stdout.write(f"[DRY RUN] cutoff={cutoff.isoformat()} — Would delete {count} unverified accounts")
            return
        deleted_total, deleted_by_model = qs.delete()
        accounts_deleted = deleted_by_model.get('account.Account', 0)
        self.stdout.write(
            f"cutoff={cutoff.isoformat()} — deleted {accounts_deleted} accounts "
            f"({deleted_total} rows total across cascades)"
        )
