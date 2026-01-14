"""
© Julius Harms, Freie Universität Berlin 2025

This file defines a basic test case that sets up data and provides utility
methods for the other test classes.
"""

from datetime import datetime, timezone, timedelta
from mock import Mock
import os

from django.http import HttpRequest
from django.test import TestCase, override_settings
from django.contrib.contenttypes.models import ContentType

import review.models
from core import (
    models as core_models,
)
from core.plugin_loader import load
import submission.models
from plugins.janeway_rqcplugin.models import RQCReviewerOptingDecisionForReviewAssignment, RQCReviewerOptingDecision, \
    RQCJournalAPICredentials
from utils import models as utils_models
from utils.testing import helpers

# Django-Debug-Toolbar gets disabled to avoid it wrapping html responses with its own templates
@override_settings(ROOT_URLCONF="plugins.janeway_rqcplugin.tests.test_urls")
@override_settings(
    DEBUG=False,
    DEBUG_TOOLBAR_CONFIG={
        'SHOW_TOOLBAR_CALLBACK': lambda request: False,
    }
)
class RQCAdapterBaseTestCase(TestCase):
    """
    Base TestCase for RQCAdapter that sets up data and provides utilities
    """

    OPT_IN = RQCReviewerOptingDecision.OptingChoices.OPT_IN
    OPT_OUT = RQCReviewerOptingDecision.OptingChoices.OPT_OUT
    UNDEFINED = RQCReviewerOptingDecision.OptingChoices.UNDEFINED

    @staticmethod
    def assign_dates_to_review_assignment(review_assignment, delta_weeks_requested , delta_days_accepted):
        review_assignment.date_requested = datetime.now(timezone.utc) - timedelta(weeks=delta_weeks_requested)
        review_assignment.date_accepted = datetime.now(timezone.utc) - timedelta(days=delta_days_accepted)
        review_assignment.date_complete = datetime.now(timezone.utc)

    @classmethod
    def create_author(cls, journal, email):

        author = helpers.create_user(
            email,
            ['author'],
            journal= journal,
        )
        author.is_active = True
        author.save()
        return author

    @classmethod
    def create_article(cls, journal, title, author, stage=submission.models.STAGE_UNDER_REVIEW):
        article = helpers.create_article(
            journal=journal,
        )
        article.title = title
        article.authors.add(author)
        article.stage = stage
        article.save()
        return article

    @classmethod
    def create_reviewer_opting_decision_for_ReviewAssignment(cls, review_assignment,
                                                             opting_status=RQCReviewerOptingDecision.OptingChoices.OPT_IN):
        opting_for_review_assignment = (RQCReviewerOptingDecisionForReviewAssignment.objects.
                                        create(review_assignment=review_assignment,
                                               opting_status=opting_status))
        return opting_for_review_assignment

    @classmethod
    def create_journal_credentials(cls, journal, journal_id, api_key):
        RQCJournalAPICredentials.objects.create(journal = journal,
                                                rqc_journal_id = journal_id,
                                                api_key = api_key)

    @classmethod
    def add_role_to_user(cls, user, role, journal):
        resolved_role = core_models.Role.objects.get(slug=role)
        core_models.AccountRole.objects.get_or_create(
            user=user, role=resolved_role, journal=journal
        )

    def login_editor(self):
        self.client.force_login(self.editor)

    def login_reviewer(self, reviewer=None):
        if reviewer is None:
            self.client.force_login(self.reviewer_one)
        else:
            self.client.force_login(reviewer)

    def create_session(self):
        session = self.client.session
        session['journal'] = self.journal_one.id
        session['user'] = self.editor.id
        session.save()

    def create_session_with_bad_user(self):
        session = self.client.session
        session['journal'] = self.journal_one.id
        session['user'] = self.bad_user.id
        session.save()
        self.client.force_login(self.bad_user)

    def create_session_with_editor(self):
        self.login_editor()
        self.create_session()

    @classmethod
    def setUpTestData(cls):
        """
        Setup the test environment.
        :return: None
        """
        roles_to_setup = [
            "reviewer",
            "editor",
        ]
        cls.press = helpers.create_press()

        # Enable the plugin
        utils_models.Plugin.objects.create(
            name='janeway_rqcplugin',
            enabled=True,
        )
        load()

        #Create Journals
        cls.journal_one, cls.journal_two = helpers.create_journals()

        helpers.create_roles(roles_to_setup)

        # Create Editor
        cls.editor = helpers.create_editor(cls.journal_one)
        cls.editor.last_name = "One"
        cls.editor.first_name = "Editor"
        cls.editor.save()

        # Create Section Editor
        cls.section_editor = helpers.create_section_editor(cls.journal_one)
        cls.section_editor.last_name = "Section Editor"
        cls.section_editor.first_name = "One"
        cls.section_editor.save()

        # Create editor will be "Chief Editor" i.e. not handling and not Section Editor
        cls.chief_editor = helpers.create_editor(cls.journal_one, **{'email': 'chief_editor@example.com'})
        cls.chief_editor.last_name = "One"
        cls.chief_editor.first_name = "Chief Editor"
        cls.chief_editor.save()

        # Create editor that will not be associated with article (no assignment, not in section)
        cls.other_editor = helpers.create_editor(cls.journal_one, **{'email': 'other_editor@example.com'})
        cls.other_editor.last_name = "One"
        cls.other_editor.first_name = "Other Editor"
        cls.other_editor.save()

        # Create use without roles
        cls.bad_user = helpers.create_second_user(cls.journal_one)

        # Set-Up author
        cls.author = helpers.create_author(cls.journal_one)

        # Create Article
        cls.active_article = helpers.create_article(
            journal=cls.journal_one,
            title = 'Active Article',
            stage = submission.models.STAGE_UNDER_REVIEW,
            date_submitted = datetime.now(timezone.utc) - timedelta(weeks=3),
            correspondence_author = cls.author,
        )
        cls.active_article.authors.add(cls.author)
        cls.active_article.save()

        # Create second article without reviews
        cls.active_article_two = helpers.create_article(
            journal=cls.journal_one,
            title = 'Active Article 2',
            stage = submission.models.STAGE_UNDER_REVIEW,
            date_submitted = datetime.now(timezone.utc) - timedelta(weeks=3),
            correspondence_author = cls.author,
        )
        cls.active_article_two.authors.add(cls.author)
        cls.active_article_two.save()

        # Add section editor to article section
        cls.active_article.section.section_editors.add(cls.section_editor)
        cls.active_article.section.editors.add(cls.chief_editor)
        cls.journal_one.save()

        # Create Reviewer 1
        cls.reviewer_one = helpers.create_peer_reviewer(cls.journal_one)
        cls.reviewer_one.is_active = True
        # Give reviewer one the 'reviewer' role in journal two
        cls.add_role_to_user(cls.reviewer_one, 'reviewer', cls.journal_two)
        cls.reviewer_one.first_name = "Reviewer"
        cls.reviewer_one.last_name = "One"
        cls.reviewer_one.save()

        # Create Reviewer 2
        cls.reviewer_two = helpers.create_peer_reviewer(cls.journal_one)
        cls.reviewer_two.is_active = True
        cls.add_role_to_user(cls.reviewer_two, 'reviewer', cls.journal_one)
        cls.reviewer_two.first_name = "Reviewer"
        cls.reviewer_two.last_name = "Two"
        cls.reviewer_two.save()

        # Give editor an EditorAssigment for active_article
        cls.editor_assignment = helpers.create_editor_assignment(
                                            cls.active_article,
                                            cls.editor,
                                        )
        # Set Up Journal two
        # Create Editor 2
        cls.editor_two = helpers.create_editor(cls.journal_two)

        # Create Review Assignment
        cls.review_assignment = helpers.create_review_assignment(
            journal=cls.journal_one,
            article=cls.active_article,
            reviewer=cls.reviewer_one,
            editor= cls.editor,
            due_date=datetime.now(timezone.utc) + timedelta(weeks=2))
        cls.assign_dates_to_review_assignment(cls.review_assignment, 2, 2)

        # Create review answer
        review.models.ReviewAssignmentAnswer.objects.create(assignment=cls.review_assignment,
                                                                   answer="<p>Test Answer<p>"
                                                                    )
        cls.review_assignment.save()

        # Create Review Assignment 2
        cls.review_assignment_two = helpers.create_review_assignment(
            journal=cls.journal_one,
            article=cls.active_article,
            reviewer=cls.reviewer_two,
            editor= cls.editor,
            due_date=datetime.now(timezone.utc) + timedelta(weeks=2),
            review_round=cls.review_assignment.review_round)
        cls.assign_dates_to_review_assignment(cls.review_assignment, 1, 1)

        # Create review answer
        review.models.ReviewAssignmentAnswer.objects.create(assignment=cls.review_assignment_two,
                                                                   answer="<p>Test Answer 2<p>"
                                                                    )
        # Set-Up API credentials for live calls:
        cls.rqc_api_key = os.environ.get('RQC_API_KEY', None)
        cls.rqc_journal_id = os.environ.get('RQC_JOURNAL_ID', None)

    @staticmethod
    def mock_messages_add(level, message, extra_tags):
        pass

    @staticmethod
    def get_method(field):
        return None

    @staticmethod
    def prepare_request_with_user(user, journal, press=None):
        """
        Build a basic request dummy object with the journal set to journal
        and the user having editor permissions.
        :param user: the user to use
        :param journal: the journal to use
        :param press: the press to use
        :return: an object with user and journal properties
        """
        request = Mock(HttpRequest)
        request.user = user
        request.GET = Mock()
        request.GET.get = RQCAdapterBaseTestCase.get_method
        request.journal = journal
        request._messages = Mock()
        request._messages.add = RQCAdapterBaseTestCase.mock_messages_add
        request.path = '/a/fake/path/'
        request.path_info = '/a/fake/path/'
        request.press = press
        request.content_type = ContentType.objects.get_for_model(user)
        request.model_content_type = request.content_type

        request.site_type = ContentType.objects.get_for_model(journal)
        request.site = press or journal
        return request