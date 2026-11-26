import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from notifications.delivery import deliver_reminders


logger = logging.getLogger(__name__)


class Command(BaseCommand):

    help = "Run periodic reminder delivery."

    def handle(self, *args, **options):

        self.stdout.write(
            "Reminder scheduler started."
        )

        while True:

            close_old_connections()

            try:

                result = deliver_reminders()

                logger.info(
                    "reminders_delivered=%s reminders_failed=%s",
                    result["delivered"],
                    result["failed"],
                )

            except Exception as exc:

                logger.error(
                    "reminder_scheduler_failed error_type=%s",
                    type(exc).__name__,
                )

            finally:
                close_old_connections()

            time.sleep(60)