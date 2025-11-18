"""
© Julius Harms, Freie Universität Berlin 2025
"""

from django.core.management.base import BaseCommand

from plugins.rqc_adapter.models import RQCDelayedCall


class Command(BaseCommand):
    """
    Tests if cron is set up correctly for RQC
    """
    help = "Tests if cron is setup correctly for RQC."

    def handle(self, *args, **options):
        """
        Tests if cron is set up correctly for RQC
        :param args: None
        :param options: None
        :return: None
        """
        # Test access to database
        try:
            delayed_calls = RQCDelayedCall.objects.all()
            self.stdout.write(self.style.SUCCESS('Cron is correctly configured for RQC. '
                                                 'Current cronjob entry is {}.'))
        except RQCDelayedCall.DoesNotExist:
            self.stdout.write(self.style.SUCCESS('Cron is not configured for RQC. '))
        return