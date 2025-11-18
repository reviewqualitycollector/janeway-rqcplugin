"""
© Julius Harms, Freie Universität Berlin 2025

This file contains the fetch_post_data function that handles the task of retrieving the data that
is sent to RQC in calls to the mhs_submission API endpoint.
"""
import logging

from django.db.models import Q

from plugins.rqc_adapter.models import RQCReviewerOptingDecision, RQCReviewerOptingDecisionForReviewAssignment, \
    RQCJournalSalt, RQCCall
from plugins.rqc_adapter.utils import convert_review_decision_to_rqc_format, create_pseudo_address, encode_file_as_b64, \
    get_editorial_decision, generate_random_salt, convert_date_to_rqc_format

MAX_SINGLE_LINE_STRING_LENGTH = 2000
MAX_MULTI_LINE_STRING_LENGTH = 200000
MAX_LIST_LENGTH = 20

def fetch_post_data(article, journal, mhs_submissionpage = '', is_interactive = False, user = None ):
    """ Generates and collects all information for a RQC submission
    :param user: User object
    :param article: Article object
    :param journal: Journal object
    :param mhs_submissionpage: str Redirect URL from RQC back to Janeway
    :param is_interactive: Boolean flag to enable interactive call mode which redirects to RQC
    :return: Dictionary of submission data
    """
    submission_data = {}

    # If the interactive flag is set user information is transmitted to RQC.
    interactive_user_email = ''
    if is_interactive and user and hasattr(user, 'email') and user.email:
        interactive_user_email = user.email

    submission_data['interactive_user'] = interactive_user_email

    # If interactive user is set the call will open RQC to grade the submission.
    # mhs_submissionpage is used by RQC to redirect the user to Janeway after grading.
    # So if interactive user is empty this should be empty as well.
    if submission_data['interactive_user']:
        submission_data['mhs_submissionpage'] = mhs_submissionpage
    else:
        submission_data['mhs_submissionpage'] = ''

    # RQC requires that single line strings don't exceed 2000 characters
    # and that multi lines string don't exceed 200 000 characters.
    # Field constraints in the models already enforce this, but we double-check for safety.
    submission_data['title'] = article.title[:MAX_SINGLE_LINE_STRING_LENGTH]

    submission_data['external_uid'] = str(article.pk)
    # The primary key is just a number because Django's auto-increment pk is used
    submission_data['visible_uid'] = str(article.pk)

    # RQC requires all datetime values to be in UTC
    # Janeway uses aware timezones and the default timezone is UTC per the general settings
    submission_data['submitted'] = convert_date_to_rqc_format(article.date_submitted)

    submission_data['author_set'] = get_authors_info(article)

    submission_data['edassgmt_set'] = get_editors_info(article)

    submission_data['review_set'] = get_reviews_info(article, journal)

    submission_data['decision'] = get_editorial_decision(article)
    return submission_data


def get_authors_info(article):
    """ Returns the authors info for an article
    :param article: Article object
    :return: List of author information
    """
    # The RQC API specifies that only information from correspondence authors
    # should be transmitted. In janeway there can only be one correspondence author
    # so the author_set will only contain one member.
    author = article.correspondence_author
    author_order = article.frozenauthor_set.filter(author=author).first()
    author_set = []
    author_info = {
        'email': author.email[:MAX_SINGLE_LINE_STRING_LENGTH],
        'firstname': author.first_name[:MAX_SINGLE_LINE_STRING_LENGTH] if author.first_name else '',
        'lastname': author.last_name[:MAX_SINGLE_LINE_STRING_LENGTH] if author.last_name else '',
        'orcid_id': author.orcid[:MAX_SINGLE_LINE_STRING_LENGTH] if author.orcid else None,
        # Add 1 because RQC author numbering starts at 1 while in Janeway counting starts at  0
        # even though default value for order is 1.
        'order_number': author_order.order+1
    }
    author_set.append(author_info)
    return author_set

def get_editors_info(article):
    """ Returns the information about the editors of the article. Retrieves saved list from
    RQCCall model if it exists.
    :param article: Article Object
    :return: List of editor info
    """
    # If a submission call has already been successfully made for the article
    # we retrieve the already submitted editor list since the RQC API requires that the field
    # doesn't change in subsequent calls.
    # Changing the assigned editors past the 'Unassigned' workflow stage
    # is probably unusual but in theory possible.
    try:
        call_record = RQCCall.objects.get(article=article)
        return call_record.editor_assignments
    except RQCCall.DoesNotExist:
        pass

    edassgmt_set = []

    # RQC requires that the list of editor assignments is no longer than 20 entries.
    # RQC distinguishes between three levels of editors.
    # 1 - handling editor, 2 - section editor, 3 - chief editor
    # One editor may appear multiple times in each role.
    # In order to avoid adding one editor with the same level twice
    # we remember the editors email + the level
    # (same editor with different level is allowed)
    seen = set()
    has_level_one_editor = False

    # Editors that are assigned to the submission are given level 3
    # Assigned section editors get level 1
    editor_assignments = article.editorassignment_set.order_by('-assigned')
    for editor_assignment in editor_assignments:
        if editor_assignment.editor_type == 'editor':
            info = get_editor_info(editor_assignment.editor, 3)
        else:
            info = get_editor_info(editor_assignment.editor, 1)
            has_level_one_editor = True

        key = (info['email'], info['level'])
        if key not in seen:
            seen.add(key)
            edassgmt_set.append(info)

    # If an editor was involved in reviewing a decision draft then that
    # editor is also associated with the submission and will be included.
    decision_drafts = article.decisiondraft_set.all()
    for draft in decision_drafts:
        # All section editors should be already included.
        # This is just here to be very safe incase the constraint that
        # a section editor has to be assigned in order to make a
        # draft decision for an article is not enforced.
        if draft.section_editor:
            info = get_editor_info(draft.section_editor, 1)
            key = (info['email'], info['level'])
            if key not in seen:
                seen.add(key)
                edassgmt_set.append(info)
                has_level_one_editor = True

        # Draft decision can be sent to chief editors even if they aren't assigned to the submission
        # Since they are involved in making the editorial decision they should be included.
        if draft.editor:
            info = get_editor_info(draft.editor, 3)
            key = (info['email'], info['level'])
            if key not in seen:
                seen.add(key)
                edassgmt_set.append(info)

    # If there is no level 1 editor we force any one of the assigned editors to be level 1
    # because the RQC API requires one level one editor.
    if not has_level_one_editor and edassgmt_set:
        edassgmt_set[0]['level'] = 1

    # The assignment set gets sorted to avoid cutting off level 1 editors.
    edassgmt_set.sort(key=lambda x: x['level'])
    return edassgmt_set[:MAX_LIST_LENGTH]

def get_editor_info(editor, level):
    """
    :param editor: Editor Object
    :param level: Level of editor
    :return: Dictionary of editor data
    """
    editor_data = {
            'email': editor.email[:MAX_SINGLE_LINE_STRING_LENGTH],
            'firstname': editor.first_name[:MAX_SINGLE_LINE_STRING_LENGTH] if editor.first_name else '',
            'lastname': editor.last_name[:MAX_SINGLE_LINE_STRING_LENGTH] if editor.last_name else '',
            'orcid_id': editor.orcid[:MAX_SINGLE_LINE_STRING_LENGTH] if editor.orcid else None,
            'level': level
        }
    return editor_data

def get_reviews_info(article, journal):
    """ Returns the info for all reviews for the given article in a list
    :param article: Article object
    :param journal: Journal object
    :return: List of review info
    """
    review_set = []
    # If a review assignment was not accepted this date field will be null.
    # Reviewers that have not accepted a review assignment are not considered for grading by RQC.

    # If data for the submission has already been sent to RQC, and it includes a reviewer
    # that has declined to review AFTER having accepted initially AND the data that was sent we
    # include said reviewer and the review assignment is treated as having been accepted, and
    # not completed.
    review_assignments = (article.reviewassignment_set.
                            # If the review round is null it was deleted (and reviews shouldn't be sent, unless they did
                            # already get sent)
                            filter(Q(rqcrevieweroptingdecisionforreviewassignment__sent_to_rqc=True)
                                   | Q(review_round__isnull=False)).
                            filter(Q(date_accepted__isnull=False) # ReviewAssignment accepted
                            | Q(date_declined__isnull=False,
                            rqcrevieweroptingdecisionforreviewassignment__sent_to_rqc=True) # Assignment was declined
                            # but only after data has been sent to RQC
                            ).select_related('rqcrevieweroptingdecisionforreviewassignment') # optimize Query
                            .order_by("date_requested"))  # To create a persistent ordering
    # Careful date_accepted gets deleted when the review is declined!
    review_num = 1
    for review_assignment in review_assignments:
        reviewer = review_assignment.reviewer
        # TODO does this code function for Non-Textbox review elements?
        review_assignment_answers = [ra.answer for ra in review_assignment.review_form_answers()]
        review_text = " ".join(review_assignment_answers)
        reviewer_has_opted_in = has_opted_in(review_assignment)

        review_data = {
            # Visible id is just supposed to identify the review as a sort of name.
            # An integer ordering by the acceptance date is used starting at 1 for the oldest review assignment.
            'visible_id': str(review_num),
            'invited': convert_date_to_rqc_format(review_assignment.date_requested) if review_assignment.date_requested else None,
            'agreed': convert_date_to_rqc_format(review_assignment.date_accepted) if review_assignment.date_accepted else None,
            'expected': convert_date_to_rqc_format(review_assignment.date_due) if review_assignment.date_due else None,
            'submitted': convert_date_to_rqc_format(review_assignment.date_complete) if review_assignment.date_complete else None,
            'text': review_text[:MAX_SINGLE_LINE_STRING_LENGTH] if reviewer_has_opted_in else '',
            # Review text is always HTML.
            # This is due to the text input being collected in the TinyMCE widget.
            'is_html': True,
            'suggested_decision': convert_review_decision_to_rqc_format(review_assignment.decision),
            'reviewer': get_reviewer_info(reviewer, reviewer_has_opted_in, journal),
            # Because RQC does not yet support attachments the attachment set is left empty.
            # review_data['attachment_set'] = get_attachment(article, review_file=article.review_file)
            'attachment_set': []
        }
        review_set.append(review_data)
        review_num = review_num + 1
        # Log reviews that are cut off. Reviews are holy so this might be relevant.
        # TODO Should something happen with the reviews that were cut off?
    if len(review_set) > 20:
        logging.info(f"RQC Call: Number of reviews exceeded {MAX_LIST_LENGTH}. {len(review_set)-MAX_LIST_LENGTH} reviews were not included in the call. Entire review_set: {review_set}")
    return review_set[:MAX_LIST_LENGTH]

def has_opted_in(review_assignment):
    """ Determines if reviewer has opted into RQC
    :param review_assignment: Review Assignment object
    :return: True if reviewer has opted in and False otherwise
    """
    try:
        opting_status = RQCReviewerOptingDecisionForReviewAssignment.objects.filter(review_assignment = review_assignment).first().opting_status
    except (AttributeError, RQCReviewerOptingDecisionForReviewAssignment.DoesNotExist):
        opting_status = None
    if opting_status == RQCReviewerOptingDecision.OptingChoices.OPT_IN:
        return True
    else:
        return False

def get_reviewer_info(reviewer, reviewer_has_opted_in, journal):
    """ Gets the reviewer's information. If the reviewer has not opted in return pseudo address and empty values instead
    :param reviewer: Reviewer object
    :param reviewer_has_opted_in: True if reviewer has opted in
    :param journal: Journal object
    :return reviewer_info: dictionary {'email': str, 'firstname': str, 'lastname': str, 'orcid_id': str}
    """
    if reviewer_has_opted_in:
        reviewer_data = {
            'email': reviewer.email[:MAX_SINGLE_LINE_STRING_LENGTH],
            'firstname': reviewer.first_name[:MAX_SINGLE_LINE_STRING_LENGTH] if reviewer.first_name else '',
            'lastname': reviewer.last_name[:MAX_SINGLE_LINE_STRING_LENGTH] if reviewer.last_name else '',
            'orcid_id': reviewer.orcid[:MAX_SINGLE_LINE_STRING_LENGTH] if reviewer.orcid else None,
        }
    # If a reviewer has opted out RQC requires that the email address is anonymised and no additional data is transmitted
    else:
        journal_salt, created = RQCJournalSalt.objects.get_or_create(journal=journal, defaults={'salt': generate_random_salt()})
        reviewer_data = {
            'email': create_pseudo_address(reviewer.email, journal_salt.salt),
            'firstname': '',
            'lastname': '',
            'orcid_id': None
        }
    return reviewer_data

# As of API version 2025-08-20, RQC does not support file attachments
# TODO: Remote files might not work with this code
def get_attachment(article, review_file):
    """ Gets the filename of the attachment and encodes its data. Attachments don't work yet on the side of RQC so in practice this should only be called with review_file=None
    :param review_file: File object
    :param article: Article object
    :return: list of dicts {filename: str, data: str}
    """
    attachment_set = []
    # File size should be no larger than 64mb
    if review_file is not None and not review_file.is_remote and review_file.get_file_size(article) <= 67108864:
        attachment_set.append({
            'filename': review_file.original_filename,
            'data': encode_file_as_b64(review_file.uuid_filename,article),
        })
    return attachment_set


