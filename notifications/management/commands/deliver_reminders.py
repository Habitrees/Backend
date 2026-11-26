from django.core.management.base import BaseCommand, CommandError

from notifications.delivery import deliver_reminders


class Command(BaseCommand):
    help = "Deliver due in-app reminders. Run periodically."

    def handle(self, *args, **options):
        result = deliver_reminders()
        self.stdout.write(f"Delivered {result['delivered']} reminders.")
        if result["failed"]:
            raise CommandError(f"{result['failed']} reminder deliveries failed.")
