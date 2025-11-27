"""
© Julius Harms, Freie Universität Berlin 2025
"""
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from plugins.rqc_adapter.utils import utc_now
from review import logic
from review.models import ReviewAssignment
from security.decorators import reviewer_user_for_assignment_required
from utils.logger import get_logger
from security import decorators
from submission import models as submission_models

from plugins.rqc_adapter import forms
from plugins.rqc_adapter.models import RQCReviewerOptingDecision, RQCDelayedCall, RQCJournalAPICredentials, \
    RQCReviewerOptingDecisionForReviewAssignment
from plugins.rqc_adapter.rqc_calls import call_mhs_submission, RQCErrorCodes
from plugins.rqc_adapter.submission_data_retrieval import fetch_post_data

logger = get_logger(__name__)

@decorators.has_journal
@decorators.editor_user_required # Also passes staff and journal managers
def manager(request):
    template = 'rqc_adapter/manager.html'
    journal = request.journal
    api_key_set = False
    try:
        credentials = RQCJournalAPICredentials.objects.get(journal=journal)
        if credentials.rqc_journal_id is not None:
            journal_id = credentials.rqc_journal_id
            form = forms.RqcSettingsForm(initial={'journal_id_field': journal_id})
        else:
            form = forms.RqcSettingsForm()

        if credentials.api_key is not None and credentials.api_key != "":
            api_key_set = True
    except RQCJournalAPICredentials.DoesNotExist:
        form = forms.RqcSettingsForm()
    return render(request, template, {'form': form, 'api_key_set': api_key_set})

@decorators.has_journal
@decorators.editor_user_required
def handle_journal_settings_update(request):
    if request.method == 'POST':
        template = 'rqc_adapter/manager.html'
        journal = request.journal
        form = forms.RqcSettingsForm(request.POST)
        user_id = request.user.id if hasattr(request, 'user') else None
        if form.is_valid():
            try:
                journal_id = form.cleaned_data['journal_id_field']
                journal_api_key = form.cleaned_data['journal_api_key_field']
                # journal_id and api_key are saved together as a pair.
                # Because journal_id and api_key only serve as valid credentials as a pair and API calls with false credentials should be avoided
                with transaction.atomic():
                    RQCJournalAPICredentials.objects.update_or_create(journal = journal, defaults={'rqc_journal_id': journal_id, 'api_key': journal_api_key})
                messages.success(request, 'RQC settings updated successfully.')
                logger.info(f'RQC settings updated successfully for journal: {journal.name} by user: {user_id}.')
            except Exception as e:
                messages.error(request, 'Settings update failed due to a system error.')
                log_settings_error(journal.name, user_id, e)
        else:
            non_field_errors = form.non_field_errors()
            for non_field_error in non_field_errors:
                messages.error(request, 'Settings update failed. ' + non_field_error)
                log_settings_error(journal.name, user_id, non_field_error)
            for field_name, field_errors in form.errors.items():
                if field_name != '__all__':
                    field_label = form.fields[field_name].label
                    for error in field_errors:
                        messages.error(request, f'{field_label}: {error}')
                        log_settings_error(journal.name, user_id, error)
            # In the case of validation errors users aren't redirect to preserve and display field and non-field errors
            return render(request, template, {'form': form})
        # Users are redirected after post to prevent double submits
        return redirect('rqc_adapter_manager')
    # Ignore non-post requests
    else:
        return redirect('rqc_adapter_manager')

def log_settings_error(journal_name, user_id, error_msg):
    logger.error(f'Failed to save RQC settings for journal {journal_name} by user: {user_id}. Details: {error_msg}')


#All one-line strings must be no longer than 2000 characters.
#All multi-line strings (the review texts) must be no longer than 200000 characters.
#Author lists must be no longer than 200 entries.
#Other lists (reviews, editor assignments) must be no longer than 20 entries.
#Attachments cannot be larger than 64 MB each.
@decorators.has_journal
@decorators.editor_user_required
def submit_article_for_grading(request, article_id):
    referrer = request.META.get('HTTP_REFERER', None)
    mhs_submission_page = referrer if referrer is not None else request.build_absolute_uri(
                                                                reverse('review_in_review',
                                                                args=[article_id]))
    article = get_object_or_404(
        submission_models.Article,
        pk=article_id,
        journal=request.journal,
    )
    journal = article.journal
    try:
        api_credentials = RQCJournalAPICredentials.objects.get(journal=journal)
    except RQCJournalAPICredentials.DoesNotExist:
        messages.error(request, 'Review Quality Collector API credentials not found.')
        return redirect(mhs_submission_page)
    user = request.user
    is_interactive = True
    post_data = fetch_post_data(article, journal, mhs_submission_page, is_interactive, user)
    response = call_mhs_submission(journal_id = api_credentials.rqc_journal_id,
                                   api_key = api_credentials.api_key,
                                   submission_id=article_id, post_data=post_data, article=article)
    if not response['success']:
        match response['http_status_code']:
            case 400:
                messages.error(request, f'Sending the data to RQC failed. '
                                        f'The message sent to RQC was malformed. '
                                        f'Details: {response["message"]}')
            case 403:
                messages.error(request, f'Sending the data to RQC failed. '
                                        f'The API key was wrong. Please check the validity of your '
                                        f'API credentials.'
                                        f'Details: {response["message"]}' ) #TODO alert editors? according to the API description editors should be alerted.
            case 404:
                messages.error(request, f'Sending the data to RQC failed. '
                                        f'The whole URL was malformed or no journal with the given '
                                        f'journal id exists at RQC. Details: {response["message"]}')
            case (RQCErrorCodes.CONNECTION_ERROR
                  | RQCErrorCodes.TIMEOUT
                  | RQCErrorCodes.REQUEST_ERROR
                  | 500
                  | 502
                  | 503
                  | 504):
                messages.error(request, f'Sending the data to RQC failed. There might be a server error on the side of RQC the data will be automatically resent shortly. Details: {response["message"]}')
                RQCDelayedCall.objects.create(remaining_tries= 10,
                                                article = article,
                                                failure_reason = str(response['http_status_code']),
                                                last_attempt_at = utc_now())
            case _:
                messages.error(request,
                                      f'Sending the data to RQC failed. Details: {response["message"]}')
        return redirect(mhs_submission_page)
    else:
        if response['http_status_code'] == 303:
            messages.success(request, 'Successfully submitted article.')
            return redirect(response['redirect_target'])
        else:
            return redirect(mhs_submission_page)

# The request must provide a journal object because the opting decision in specific to the journal
# The user must be a reviewer since only reviewers should be able to opt in or out
@decorators.has_journal
@reviewer_user_for_assignment_required
def set_reviewer_opting_status(request, assignment_id):
    if request.method == 'POST':
        form = forms.ReviewerOptingForm(request.POST)
        if form.is_valid():

            opting_status = form.cleaned_data['status_selection_field']

            # Logic checks request.GET for the access code.
            access_code = logic.get_access_code(request)
            if access_code is None:
                access_code = request.POST.get('access_code', None)

            # Get the ReviewAssignment object.
            try:
                if access_code is not None:
                    assignment = ReviewAssignment.objects.get(
                        Q(pk=assignment_id)
                        & Q(is_complete=False)
                        & Q(access_code=access_code)
                        & Q(article__stage=submission_models.STAGE_UNDER_REVIEW)
                    )
                else:
                    assignment = ReviewAssignment.objects.get(
                        Q(pk=assignment_id)
                        & Q(is_complete=False)
                        & Q(reviewer=request.user)
                        & Q(article__stage=submission_models.STAGE_UNDER_REVIEW)
                    )
            except ReviewAssignment.DoesNotExist:
                # This shouldn't occur normally.
                # Without the assignment the redirect url to the review form cannot be generated.
                # In order to send the user back to the review form the HTTP_REFERER is the best bet.
                logger.error(f'RQC: Error while setting reviewer opting status. '
                             f'ReviewAssignment {assignment_id} not found.')
                messages.error(request, 'An unexpected error occurred while '
                                        'updating your participation choice.')
                referer = request.META.get('HTTP_REFERER')
                if referer:
                    return redirect(referer)
                else:
                    return redirect('core_dashboard')

            user = assignment.reviewer

            decision, created = RQCReviewerOptingDecision.objects.update_or_create(reviewer = user, journal= request.journal, defaults={'opting_status': opting_status, 'opting_date': utc_now()})
            if opting_status == RQCReviewerOptingDecision.OptingChoices.OPT_IN:
                messages.info(request, 'Thank you for choosing to participate in RQC!')
            else:
                messages.info(request, 'Thank you for your response. Your preference has been recorded.')

            # Check if the Review Assignment is frozen (see also the is_frozen property
            # of RQCReviewerOptingDecisionForReviewAssignment)
            # Not Frozen means data was not yet received by RQC
            # and the assignment is ongoing meaning accepted but not complete and not declined.
            # If the Review Assignment is not frozen we update the opting status to reflect
            # the selected value.
            RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
                review_assignment=assignment,
                sent_to_rqc=False,
                review_assignment__is_complete=False,
                review_assignment__date_declined__isnull=True,
                review_assignment__date_accepted__isnull=False,
                review_assignment__date_accepted__year=utc_now().year
            ).update(opting_status=opting_status, decision_record=decision)

            return redirect(
                logic.generate_access_code_url("do_review", assignment, access_code)
            )
    else:
        return redirect('core_dashboard')