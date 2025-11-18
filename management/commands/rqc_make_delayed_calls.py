"""
© Julius Harms, Freie Universität Berlin 2025
"""

from datetime import timedelta
from time import sleep

from django.core.management.base import BaseCommand

from plugins.rqc_adapter.models import RQCDelayedCall, RQCJournalAPICredentials
from plugins.rqc_adapter.rqc_calls import call_mhs_submission
from plugins.rqc_adapter.submission_data_retrieval import fetch_post_data
from plugins.rqc_adapter.utils import utc_now
from utils.logger import get_logger

logger = get_logger(__name__)

class Command(BaseCommand):
    """
    Retries failed RQC Calls.
    """
    help = "Retries failed RQC Calls."

    def add_arguments(self, parser):
        parser.add_argument('--action', default="")

    def handle(self, *args, **options):
        """
        Retries failed RQC calls.
        :param args: None
        :param options: None
        :return: None
        """
        queue = RQCDelayedCall.objects.all().order_by('-last_attempt_at')
        for call in queue:
            if call.is_valid:
                article = call.article
                article_id = call.article.pk
                journal = call.article.journal
                post_data = fetch_post_data(article = article, journal = journal)
                try:
                    credentials = RQCJournalAPICredentials.objects.get(journal=journal)
                except RQCJournalAPICredentials.DoesNotExist:
                    logger.warning("Delayed call to RQC was attempted but no RQC API credentials found.")
                    return
                response = call_mhs_submission(credentials.rqc_journal_id, credentials.api_key, submission_id=article_id, post_data=post_data, article=article)
                logger.info(f"Delayed call to RQC was attempted for article {article_id}:{article.title}.")
                call.remaining_tries = call.remaining_tries - 1
                if not response['success']:
                    logger.info(f"Delayed call to RQC failed for article {article_id}:{article.title}.")
                    call.last_attempt_at = utc_now()
                    call.save()
                    # If a call is unsuccessful we should stop trying for the day.
                    return
                else:
                    logger.info(f"Delayed call to RQC succeeded for article {article_id}:{article.title}.")
                    call.delete()
            else:
                call.delete()
            sleep(1)