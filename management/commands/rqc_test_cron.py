"""
© Julius Harms, Freie Universität Berlin 2025
"""

from django.core.management.base import BaseCommand

from plugins.janeway_rqcplugin.models import RQCDelayedCall


class Command(BaseCommand):
    """
    Tests if cron is set up correctly for RQC
    """
    help = "Tests if cron is setup correctly for RQC."
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output-path',
            help='Path to write the result to. If not specified, prints to stdout.'
        )

    def handle(self, *args, **options):
        """
        Tests if cron is set up correctly for RQC
        :param args: None
        :param options: None
        :return: None
        """
        output_path = options.get('output_path')
        
        # Test access to database
        try:
            delayed_calls = RQCDelayedCall.objects.count()
            message = 'SUCCESS'
            self.stdout.write(self.style.SUCCESS('Cron is correctly configured for RQC. '))
        except Exception as e:
            message = f'FAILURE: {str(e)}'
            self.stdout.write(self.style.ERROR(message))
            
        if output_path:
            with open(output_path, 'w') as f:
                f.write(message)
        return