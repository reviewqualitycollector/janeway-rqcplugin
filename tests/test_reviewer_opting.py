"""
© Julius Harms, Freie Universität Berlin 2025
"""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils import timezone

from plugins.rqc_adapter.models import RQCReviewerOptingDecision, RQCJournalAPICredentials, \
    RQCReviewerOptingDecisionForReviewAssignment
from plugins.rqc_adapter.tests.base_test import RQCAdapterBaseTestCase
from utils.testing import helpers

class TestReviewerOpting(RQCAdapterBaseTestCase):
    review_form_view = 'do_review'
    review_form_template = 'review/review_form.html'
    opting_form_template = 'rqc_adapter/reviewer_opting_form.html'
    opting_from_post_view = 'rqc_adapter_set_reviewer_opting_status'
    accept_review_request_view = 'accept_review'

    post_opting_form_url = reverse(opting_from_post_view)

    def create_opt_in_form_data(self, assignment_id=None):
        data = {'status_selection_field': self.OPT_IN}
        if assignment_id:
            data['assignment_id'] = assignment_id
        return data

    def create_opt_out_form_data(self, assignment_id=None):
        data = {'status_selection_field': self.OPT_OUT}
        if assignment_id:
            data['assignment_id'] = assignment_id
        return data

    def post_opting_status(self, form_data, follow=False):
        return self.client.post(
            self.post_opting_form_url,
            data=form_data,
            follow=follow
        )

    def get_review_form(self, assignment_id=None, access_code=None):
        if access_code is None:
            return self.client.get(
                reverse(self.review_form_view,
                args=[assignment_id]))
        else:
            return self.client.get(
                reverse(self.review_form_view,
                args=[assignment_id]), data={'access_code': access_code})

    def create_opting_status(self, journal_field, decision, opting_date=None):
        if opting_date:
            return RQCReviewerOptingDecision.objects.create(reviewer=self.reviewer_one,
                                                    journal=journal_field,
                                                    opting_status=decision,
                                                    opting_date=opting_date)
        else:
            # Created with current time as default
            return RQCReviewerOptingDecision.objects.create(reviewer= self.reviewer_one,
                                                     journal=journal_field,
                                                     opting_status=decision)

    def create_session(self, param_journal=None, param_reviewer=None):
        session = self.client.session
        if param_journal is None:
            session['journal'] = self.journal_one.id
        else:
            session['journal'] = param_journal.id
        if param_reviewer is None:
            session['user'] = self.reviewer_one.id
        else:
            session['user'] = param_reviewer.id
        session.save()

    def create_session_with_reviewer(self, param_journal=None, param_reviewer=None):
        self.login_reviewer(param_reviewer)
        self.create_session(param_journal, param_reviewer)

    def assert_opting_form_template_used(self, response):
        self.assertTemplateUsed(response, self.opting_form_template)

    def assert_opting_decision_exists(self):
        self.assertTrue(
            RQCReviewerOptingDecision.objects.filter(
                reviewer=self.reviewer_one,
                opting_status=self.OPT_IN
            ).exists()
        )

    def setUp(self):
        super().setUp()
        self.create_journal_credentials(self.journal_one, 1, 'test')
        self.create_journal_credentials(self.journal_two, 2, 'test')

        self.create_session_with_reviewer()
        # Create second Review Assignment
        # Set-Up author
        self.author_two = self.create_author(self.journal_two, 'author_two@email.com')
        # Create Article
        self.article_two = self.create_article(self.journal_two, 'Article 2', self.author_two)

        self.review_assignment_two = helpers.create_review_assignment(
            journal=self.journal_two,
            article=self.article_two,
            reviewer=self.reviewer_one,
            editor=self.editor_two,
            due_date= timezone.now() + timedelta(weeks=2))

        self.review_assignment_two.date_accepted = timezone.now()

        # Create third Review Assignment in journal_one
        self.article_three = self.create_article(self.journal_one, 'Article 3', self.author)
        self.review_assignment_three = helpers.create_review_assignment(
            journal=self.journal_one,
            article=self.article_three,
            reviewer=self.reviewer_one,
            editor= self.editor,
            due_date= timezone.now() + timedelta(weeks=2)
        )
        self.review_assignment_three.date_accepted = timezone.now()

        self.review_assignment_two.save()
        self.review_assignment_three.save()

    def test_opting_status_set(self):
        """Test creation of opting status when form is submitted and redirection."""
        response = self.post_opting_status(form_data=self.create_opt_in_form_data())
        # Redirect after POST
        self.assertEqual(response.status_code, 302)
        # Created Opting status
        self.assert_opting_decision_exists()

    def test_opting_status_set_opt_out(self):
        """Test creation of opting status when form is submitted and redirection."""
        response = self.post_opting_status(form_data=self.create_opt_out_form_data())
        # Redirect after POST
        self.assertEqual(response.status_code, 302)
        # Created Opting status
        self.assertTrue(
            RQCReviewerOptingDecision.objects.filter(
                reviewer=self.reviewer_one,
                opting_status=self.OPT_OUT
            ).exists()
        )
    def test_active_review_assignments_get_status_update(self):
        """Correctly updates RQCOptingStatusForReviewAssignment for active review assignments."""
        self.create_reviewer_opting_decision_for_ReviewAssignment(review_assignment=self.review_assignment,
                                                                  opting_status=self.UNDEFINED)

        self.get_review_form(assignment_id=self.review_assignment.id)
        self.post_opting_status(form_data=self.create_opt_in_form_data(
            assignment_id=self.review_assignment.id))
        self.assert_opting_decision_exists()
        # Updated Opting-Decision for Review Assignment
        self.assertTrue(RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
            review_assignment=self.review_assignment,
            opting_status=self.OPT_IN).exists())

    # Declined or complete reviews or reviews that were sent to RQC
    # do not get their opting status updated.
    def set_status_undefined_for_review_assignment_three(self):
        review_assignment_opting_status = self.create_reviewer_opting_decision_for_ReviewAssignment(
            self.review_assignment_three,
            self.UNDEFINED)
        return review_assignment_opting_status

    def assert_review_assignment_three_not_updated(self):
        self.assertTrue(RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
            review_assignment=self.review_assignment_three,
            opting_status=self.UNDEFINED).exists())

    def test_declined_review_assignments_do_not_status_update(self):
        """Does not update RQCOptingStatusForReviewAssignment for declined review assignments."""
        review_assignment_opting_status = self.set_status_undefined_for_review_assignment_three()
        review_assignment_opting_status.review_assignment.date_declined = timezone.now()
        self.post_opting_status(form_data=self.create_opt_in_form_data(assignment_id=self.review_assignment.id))
        self.assert_review_assignment_three_not_updated()

    def test_complete_review_assignments_do_not_status_update(self):
        """Does not update RQCOptingStatusForReviewAssignment for complete review assignments."""
        review_assignment_opting_status = self.set_status_undefined_for_review_assignment_three()
        review_assignment_opting_status.review_assignment.is_complete = True
        self.post_opting_status(form_data=self.create_opt_in_form_data(assignment_id=self.review_assignment.id))
        self.assertTrue(RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
            review_assignment=self.review_assignment_three,
            opting_status=self.UNDEFINED).exists())

    def test_sent_review_assignments_do_not_status_update(self):
        """Does not update RQCOptingStatusForReviewAssignment for already sent review assignments."""
        review_assignment_opting_status = self.set_status_undefined_for_review_assignment_three()
        review_assignment_opting_status.sent_to_rqc = True
        self.post_opting_status(form_data=self.create_opt_in_form_data(assignment_id=self.review_assignment.id))

#Integration-Tests

    def test_opting_form_shown_if_no_opting_status_present(self):
        """Form is shown on the review form if no opting status is present."""
        # Open the review form
        response = self.get_review_form(assignment_id=self.review_assignment.id)
        self.assertTemplateUsed(response, self.review_form_template)
        self.assert_opting_form_template_used(response)

    def redirect_test_helper(self):
        form_data = self.create_opt_in_form_data(assignment_id=self.review_assignment.id)
        response = self.post_opting_status(form_data=form_data, follow=True)
        # Created Opting status
        self.assert_opting_decision_exists()
        # Redirected to review_form with correct url
        self.assertTemplateUsed(response, self.review_form_template)
        return response

    def test_redirect_to_review_form(self):
        """Test redirection to review form."""
        self.get_review_form(assignment_id=self.review_assignment.id)
        response = self.redirect_test_helper()
        final_url = response.request['PATH_INFO']
        expected_url = reverse(self.review_form_view, args=[self.review_assignment.id])
        self.assertEqual(final_url, expected_url)

    def test_opting_form_not_shown(self):
        """Form is not shown on the review form if the reviewer already has a valid opting status."""
        self.create_opting_status(self.journal_one, self.OPT_IN)
        response = self.get_review_form(assignment_id=self.review_assignment.id)
        self.assertTemplateNotUsed(response,self.opting_form_template)

    def test_opting_form_shown_invalid_opting_status(self):
        """Form is shown if the reviewer has an invalid (old) opting status."""
        opting_decision = self.create_opting_status(self.journal_one,
                                                    self.OPT_IN,
                                                    )
        opting_decision.opting_date = timezone.now() - timedelta(weeks=200)
        opting_decision.save()
        response = self.get_review_form(assignment_id=self.review_assignment.id)
        self.assertTemplateUsed(response, self.opting_form_template)

    def test_opting_form_shown_in_second_journal(self):
        """Form is shown in second journal even if reviewer already
        has a valid opting status in another journal."""
        self.client.logout()
        # Create OPT-In status in journal one
        self.create_opting_status(self.journal_one, self.OPT_IN)
        # Log-In in Journal two
        self.create_session_with_reviewer(param_journal=self.journal_two)
        # Go to review assignment in Journal two. It's important to explicitly use the
        # domain of journal two.
        response = self.client.get(
            reverse(self.review_form_view,
            args=[self.review_assignment_two.id]),HTTP_HOST=self.journal_two.domain)
        self.assertTemplateUsed(response, self.opting_form_template)

    @patch('plugins.rqc_adapter.views.set_reviewer_opting_status')
    def test_non_reviewers_can_not_set_opting_status(self,  mock_set_opting_status):
        """Tests if non-reviewers can not set opting status."""
        self.client.logout()
        self.client.force_login(self.bad_user)
        self.create_session(self.journal_one, self.bad_user)
        self.post_opting_status(form_data=self.create_opt_in_form_data())
        # The review_user_required decorator should intervene and stop the post-function
        # from being called.
        mock_set_opting_status.assert_not_called()

    def prepare_review_assignment(self):
        self.review_assignment.date_accepted = None
        self.is_complete = False
        self.review_assignment.save()


    def test_opting_for_review_assignment_created_with_opt_in(self):
        """Test that RQCOptingDecisionForReviewAssignment is created when review request is accepted."""
        self.prepare_review_assignment()
        opting_decision = self.create_opting_status(self.journal_one, self.OPT_IN)
        self.client.post(reverse(self.accept_review_request_view,args=[ self.review_assignment.pk]))
        self.assertTrue(RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
            review_assignment=self.review_assignment,
            opting_status=self.OPT_IN,
            decision_record=opting_decision,
        ).exists())

    def test_opting_for_review_assignment_created_with_opt_out(self):
        """Test that RQCOptingDecisionForReviewAssignment is correctly
        created when review request is accepted
        and opting status is 'opt out'"""
        self.prepare_review_assignment()
        opting_decision = self.create_opting_status(self.journal_one, self.OPT_OUT)
        self.client.post(reverse(self.accept_review_request_view, args=[self.review_assignment.id]))
        self.assertTrue(RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
            review_assignment=self.review_assignment,
            opting_status=self.OPT_OUT,
            decision_record=opting_decision,
        ).exists())

    def test_opting_for_review_assignment_created_with_undefined(self):
        """Test that RQCOptingDecisionForReviewAssignment is created when review request is accepted."""
        self.prepare_review_assignment()
        self.client.post(reverse(self.accept_review_request_view, args=[self.review_assignment.pk]))
        self.assertTrue(RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
            review_assignment=self.review_assignment,
            opting_status=self.UNDEFINED,
        ).exists())

    def test_opting_for_review_assignment_not_created_without_credentials(self):
        self.prepare_review_assignment()
        """Test that RQCOptingDecisionForReviewAssignment is not created when credentials are not provided."""
        RQCJournalAPICredentials.objects.all().delete()
        self.client.post(reverse(self.accept_review_request_view, args=[self.review_assignment.pk]))
        self.assertFalse(RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
            review_assignment=self.review_assignment,
            opting_status=self.UNDEFINED,
        ).exists())