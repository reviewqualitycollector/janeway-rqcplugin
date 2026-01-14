"""
© Julius Harms, Freie Universität Berlin 2025
"""

import base64
import hashlib
import os
import secrets
import string

from datetime import datetime, timezone

from django.conf import settings

from plugins.janeway_rqcplugin.models import RQCReviewerOptingDecision, RQCJournalSalt
from review.models import RevisionRequest

# As of API version 2023-09-06, RQC does not support file attachments
def encode_file_as_b64(file_uuid: str, article_id: str) -> str:
    """
    Encodes the file as a base64 binary string.
    :param file_uuid: File UUID
    :param article_id: Article ID
    :return: base64 encoded file
    """
    file_path = os.path.join(settings.BASE_DIR, 'files', 'articles', article_id, file_uuid)
    with open(file_path, "rb") as f:
        encoded_file = base64.b64encode(f.read()).decode('utf-8')
    return encoded_file


def convert_review_decision_to_rqc_format(decision_string: str) -> str:
    """
    Maps the string representation of the reviewers decision to the string representation in RQC.
    :param decision_string: The string representation of the reviewers decision.
    :return: The string representation of the reviewers decision in RQC format.
    """
    match decision_string:
        case 'accept':
            return 'ACCEPT'
        case 'minor_revisions':
            return 'MINORREVISION'
        case 'major_revisions':
            return 'MAJORREVISION'
        case 'reject':
            return 'REJECT'
        case _:
            return ''

def get_editorial_decision(article):
    """
    Gets the (most recent) editorial decision for the article. The default is empty "".
    :param article: Article object
    :return: String of the editorial decision
    """
    if article.is_accepted():
        return 'ACCEPT'
    elif article.date_declined is not None:
        return 'REJECT'
    else:
        revision_request = RevisionRequest.objects.filter(article=article).order_by('-date_requested').first()
        if revision_request is None:
            return ''
        # Conditional accept gets mapped to 'minor revisions' in RQC.
        if revision_request.type == 'minor_revisions' or revision_request.type == 'conditional_accept':
            return 'MINORREVISION'
        else:
            return 'MAJORREVISION'

def create_pseudo_address(email, salt):
    """
    Create a pseudo email address.
    :param email: Email address
    :param salt: Salt to use for the pseudo address
    :return: String of the pseudo address
    """
    combined = email + salt
    hash_obj = hashlib.sha1(combined.encode())
    hash_hex = hash_obj.hexdigest()
    pseudo_address = hash_hex + "@example.edu"
    return pseudo_address

def generate_random_salt(length=12):
    """
    Generate a random salt string of specified length.
    Uses a mix of lowercase letters, uppercase letters, and digits.
    :param length: Length of the salt string.
    :return: String of the salt value
    """
    characters = string.ascii_letters + string.digits
    salt = ''.join(secrets.choice(characters) for _ in range(length))
    while RQCJournalSalt.objects.filter(salt=salt).exists():
        salt = ''.join(secrets.choice(characters) for _ in range(length))
    return salt

def has_opted_in_or_out(user, journal):
    """
    Check if a user has opted in/out or not.
    :param user: Account object
    :param journal: Journal object
    :return: Boolean
    """
    try:
        opting_decision = RQCReviewerOptingDecision.objects.filter(reviewer=user, journal=journal, opting_date__year = utc_now().year).first()
        if opting_decision is not None and opting_decision.is_valid:
            opting_status = opting_decision.opting_status
            if opting_status is not None and (opting_status == RQCReviewerOptingDecision.OptingChoices.OPT_IN or opting_status == RQCReviewerOptingDecision.OptingChoices.OPT_OUT):
                return True
        else:
            return False
    except RQCReviewerOptingDecision.DoesNotExist:
        return False

def utc_now():
    """
    Returns the current UTC datetime as an aware datetime object.
    """
    return datetime.now(timezone.utc)

def convert_date_to_rqc_format(date: datetime | None = None) -> str:
    """
    :param date: datetime Date to convert to RQC format.
    :return: Current time in UTC in RQC format.
    """
    if date is None:
        return utc_now().strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        return date.strftime('%Y-%m-%dT%H:%M:%SZ')