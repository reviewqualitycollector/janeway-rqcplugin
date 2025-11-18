"""
© Julius Harms, Freie Universität Berlin 2025

This command installs the cronjob that makes delayed calls to the RQC API.
"""

import os
import shutil
from time import sleep

from utils.logger import get_logger

from django.core.management.base import BaseCommand
from django.conf import settings

try:
    import crontab
except (ImportError, ModuleNotFoundError):
    crontab = None

logger = get_logger(__name__)

class Command(BaseCommand):
    """
    Installs the cron task for retrying failed RQC calls.
    """

    help = ("Installs the cron task for retrying failed RQC calls. You can "
            "customize when delayed calls to RQC are made."
            "Default is '0 8 * *' which means calls are made at 8am every"
            "day. ")

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['install', 'remove', 'status'],
            default='install',
            help='Action to perform: install, remove, or check status of the cronjob'
        )
        parser.add_argument(
            '--time',
            type=int,
            default=8,
            help='Time at which the daily RQC cronjob is run. Default is 8 for 8am.'
                 'The value should be between 0 and 23.)'
        )

    def get_crontab(self):
        if not shutil.which('crontab'):
            self.stdout.write(self.style.ERROR((
                'WARNING: crontab command not found. Please install cron on your system.'
                    )
                )
            )
            return None
        if not crontab:
            self.stdout.write(
                self.style.WARNING('WARNING: crontab python module is not installed.')
            )
            return None
        tab = crontab.CronTab(user=True)  # load current user as cron user
        return tab

    @staticmethod
    def find_rqc_cronjob(tab, command_name):
        for job in tab:
            if command_name in job.command:
                return job
        return None

    def install_rqc_cronjob(self, time=8):
        """Installs RQC cronjob.
        :param time: time of cronjob to install. Value between 0 and 23
        """
        tab = self.get_crontab()

        if tab is None:
            return
        if  time < 0 or time > 23:
            self.stdout.write(self.style.ERROR('Could not install RQC cronjob. '
                                               'Please enter a time value between 0 and 23'))
            return

        # Get command
        virtualenv = os.environ.get('VIRTUAL_ENV', None)
        django_command = "{0}/manage.py {1}".format(settings.BASE_DIR, 'rqc_make_delayed_calls')
        if virtualenv:
            command = '/%s/bin/python3 %s' % (virtualenv, django_command)
        else:
            command = '%s' % django_command
        cron_job = tab.new(command)

        # Set time
        if time is not None:
            cron_job.setall(f'0 {time} * * *')
        else:
            cron_job.setall('0 8 * * *')
        tab.write()

        # Write status
        self.stdout.write(
            self.style.SUCCESS('Successfully installed RQC cronjob.')
        )
        logger.info(f'Successfully installed RQC cronjob.')
        self.stdout.flush()

    def remove_rqc_cronjob(self, command_name='rqc_make_delayed_calls'):
        """Removes RQC cronjob."""
        tab = self.get_crontab()
        rqc_cronjob = self.find_rqc_cronjob(tab, command_name)
        if tab is None:
            self.stdout.write(self.style.ERROR('Could not remove RQC cronjob. Perhaps RQC cronjob '
                             'or cron is not installed.')
                              )
            return
        if rqc_cronjob is not None:
            tab.remove(rqc_cronjob)
            tab.write()
            self.stdout.write(self.style.SUCCESS('Successfully removed RQC cronjob')
                              )

    def show_status(self):
        """Show the status of the RQC cronjob."""
        tab = self.get_crontab()
        if tab is None:
            self.stdout.write(self.style.ERROR('Could not find crontab. Perhaps cron is not installed.'))
            return
        rqc_cronjob = self.find_rqc_cronjob(tab)
        if rqc_cronjob is None:
            self.stdout.write(self.style.ERROR('RQC cronjob is not installed.'))
            return
        else:
            self.stdout.write(self.style.SUCCESS('RQC cronjob is installed. '
                                                 'Current cronjob entry is {}. '
                               ''.format(rqc_cronjob)))
            return

    def check_config(self):
        """
        Temporarily installs a cron job that tests if cron is correctly configured.
        """
        tab = self.get_crontab()
        if tab is None:
            self.stdout.write(self.style.ERROR('Could not find crontab. Perhaps the crontab python module is not installed.'))
        # Get command
        virtualenv = os.environ.get('VIRTUAL_ENV', None)
        django_command = "{0}/manage.py {1}".format(settings.BASE_DIR, 'rqc_test_cron')
        if virtualenv:
            command = '/%s/bin/python3 %s' % (virtualenv, django_command)
        else:
            command = '%s' % django_command
        cron_job = tab.new(command)
        cron_job.setall('* * * * *')
        tab.write()
        # Wait for the cronjob to be executed
        sleep(61)
        # Check if the command was successful

        self.remove_rqc_cronjob('rqc_test_cron')

    def handle(self, *args, **options):
        """
        Manages RQC cronjob based on the specified action and schedule.
        """
        action = options['action']
        if action == 'install':
            self.install_rqc_cronjob(options['time'])
        elif action == 'remove':
            self.remove_rqc_cronjob()
        elif action == 'status':
            self.show_status()
        elif action == 'check_config':
            self.check_config()
