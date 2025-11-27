"""
© Julius Harms, Freie Universität Berlin 2025

This file contains tests for the manager template and the associated
form uses to set the journals api credentials.
"""
import os
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.http import QueryDict
from django.urls import reverse

from plugins.rqc_adapter.forms import RqcSettingsForm
from plugins.rqc_adapter.models import RQCJournalAPICredentials
from plugins.rqc_adapter.tests.base_test import RQCAdapterBaseTestCase
from plugins.rqc_adapter.views import handle_journal_settings_update

has_api_credentials_env = os.getenv("RQC_API_KEY") and os.getenv("RQC_JOURNAL_ID")

class TestManager(RQCAdapterBaseTestCase):

    def post_manager_form(self, form_data):
        return self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data)


    def create_mock_post_request(self, journal_id, api_key):
        request = self.prepare_request_with_user(self.editor, self.journal_one, self.press)
        post_data = QueryDict(mutable=True)
        post_data.update({
            'journal_id_field': journal_id,
            'journal_api_key_field': api_key,
        })
        request.method = 'POST'
        request.POST = post_data
        return request


class TestManagerMockCalls(TestManager):

   # Data with valid format
    mock_valid_data = {
            'journal_id_field': 9,
            'journal_api_key_field': "test",
        }

    def setUp(self):
        super().setUp()
        # In this class the calls to the mhs_apikeycheck endpoint are mocked
        patcher = patch('plugins.rqc_adapter.forms.call_mhs_apikeycheck')
        self.mock_call = patcher.start()
        self.addCleanup(patcher.stop)

# Unit-Tests

    def test_valid_credentials_saved_to_database(self):
        """Valid submission creates database record"""
        self.mock_call.return_value =  {
        'success': True,
        'http_status_code': 200,
        'message': 'Validation Successful',
        'redirect_target': None,
        }
        # Create mock request
        request = self.create_mock_post_request(self.mock_valid_data.get("journal_id_field"), self.mock_valid_data.get("journal_api_key_field"))

        response = handle_journal_settings_update(request)

        # Status Code to redirect
        self.assertEqual(response.status_code, 302)
        # Check that credentials were created
        self.assertTrue(
            RQCJournalAPICredentials.objects.filter(
                journal=self.journal_one,
                rqc_journal_id=self.mock_valid_data.get("journal_id_field"),
                api_key=self.mock_valid_data.get("journal_api_key_field")
            ).exists()
        )
        self.mock_call.assert_called_once_with(self.mock_valid_data.get("journal_id_field"),
                                                self.mock_valid_data.get("journal_api_key_field"))

    def test_existing_credentials_updated_not_duplicated(self):
        """Resubmitting updates existing record"""
        self.mock_call.return_value =  {
        'success': True,
        'http_status_code': 200,
        'message': 'Validation Successful',
        'redirect_target': None,
        }

        self.create_session_with_editor()
        RQCJournalAPICredentials.objects.create(journal=self.journal_one, rqc_journal_id=1, api_key='test')
        form_data = self.mock_valid_data
        self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data)
        self.assertTrue(
            RQCJournalAPICredentials.objects.filter(
                journal=self.journal_one,
                rqc_journal_id=self.mock_valid_data.get('journal_id_field'),
                api_key=self.mock_valid_data.get('journal_api_key_field')
            ).exists()
        )
        self.assertEqual(RQCJournalAPICredentials.objects.filter(journal=self.journal_one).count(), 1)
        self.mock_call.assert_called_once_with(self.mock_valid_data.get('journal_id_field'),
                                               self.mock_valid_data.get('journal_api_key_field'))

    def test_empty_fields_rejected(self):
        """Test that empty required fields show errors"""
        self.create_session_with_editor()
        form_data = {
        }
        response = self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data)
        form = response.context['form']
        self.assertFormError(form, 'journal_id_field', 'This field is required.')
        self.assertFormError(form, 'journal_api_key_field', 'This field is required.')
        self.mock_call.assert_not_called()

    def test_invalid_api_key_format_rejected(self):
        """Malformed API keys are rejected"""
        # Create mock request with invalid journal_api_key
        # Non-alphanumeric values are rejected
        self.create_session_with_editor()
        form_data = {
            'journal_id_field': 6,
            'journal_api_key_field': "@test?",
        }
        response = self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data)
        self.assertFormError(response.context['form'], 'journal_api_key_field', 'The API key must only contain alphanumeric characters.')
        self.mock_call.assert_not_called()

    def test_invalid_journal_id_format_rejected(self):
        """Invalid journal IDs are rejected"""
        # Create mock request with invalid journal_id
        self.create_session_with_editor()
        form_data = {
            'journal_id_field': "test",
            'journal_api_key_field': "test",
        }
        response = self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data)
        self.assertFormError(response.context['form'], 'journal_id_field', 'Journal ID must be a number')
        self.mock_call.assert_not_called()

    def test_manager_contains_form(self):
        self.create_session_with_editor()
        response = self.client.get(reverse('rqc_adapter_manager'))
        form = response.context['form']
        self.assertTrue(form is not None)
        self.assertIsInstance(form, RqcSettingsForm)

    def test_redirect_after_valid_post(self):
        """
        Tests 'happy' path where editor deposits valid data a database record is created and user is redirected.
        Note that this requires rqc_api_key and rqc_journal_id to be present as environment variables.
        See also setUpData in base_test.
        """
        self.mock_call.return_value = {
        'success': True,
        'http_status_code': 200,
        'message': 'Validation Successful',
        'redirect_target': None,
        }

        self.create_session_with_editor()
        form_data = self.mock_valid_data
        response = self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data)
        # Redirect after post
        self.assertEqual(response.status_code, 302)
        self.mock_call.assert_called_once_with(self.mock_valid_data.get('journal_id_field'),
                                               self.mock_valid_data.get('journal_api_key_field'))

    def test_redirect_to_manager_after_valid_post(self):
        """
        Tests 'happy' path where editor deposits valid data a database record is created and user is redirected to manager page.
        """
        self.mock_call.return_value = {
        'success': True,
        'http_status_code': 200,
        'message': 'Validation Successful',
        'redirect_target': None,
        }
        # Valid example data
        self.create_session_with_editor()
        form_data = self.mock_valid_data
        response = self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data, follow=True)
        # Database objects were created
        self.assertTrue(RQCJournalAPICredentials.objects.filter(journal=self.journal_one,
                                                                rqc_journal_id=self.mock_valid_data.get('journal_id_field'),
                                                                api_key = self.mock_valid_data.get('journal_api_key_field')).exists())
        # Manager template is given in response after redirect
        self.assertTemplateUsed(response, 'rqc_adapter/manager.html')
        self.mock_call.assert_called_once_with(self.mock_valid_data.get('journal_id_field'),
                                               self.mock_valid_data.get('journal_api_key_field'))

    def test_successful_submission_shows_success_message(self):
        """User gets feedback on successful submission"""
        self.create_session_with_editor()
        response = self.post_manager_form(self.mock_valid_data)
        messages = list(get_messages(response.wsgi_request))
        self.assertIn('RQC settings updated successfully.', [m.message for m in messages])

# Unit-Test: Form displays error messages
    def test_form_errors_displayed(self):
        """Validation errors are shown next to relevant fields"""
        self.create_session_with_editor()
        form_data = {
            'journal_id_field': "test",
            'journal_api_key_field': "_!test",
        }
        form = RqcSettingsForm(form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('journal_id_field', form.errors)
        self.assertIn('journal_api_key_field', form.errors)

    def test_form_errors_displayed_in_template(self):
        """Validation errors are shown next to relevant fields"""
        self.create_session_with_editor()
        form_data = {
            'journal_id_field': "test",
            'journal_api_key_field': "_!test",
        }
        response = self.post_manager_form(form_data)
        self.assertContains(response, "Journal ID must be a number")
        self.assertContains(response, "The API key must only contain alphanumeric characters.")

    def test_form_retains_data_after_validation_error(self):
        """User doesn't lose their input if validation fails"""
        self.create_session_with_editor()
        form_data = {
            'journal_id_field': "test",
            'journal_api_key_field': "_!test",
        }
        response = self.post_manager_form(form_data)
        form = response.context['form']
        self.assertFalse(form.is_valid())
        self.assertContains(response, 'value="test"')

    # Integration Tests
    def test_anonymous_user_redirected_to_login(self):
        """
        Test whether anonymous user is redirected to login page.
        """
        # Valid example data
        form_data = {
            'journal_id_field': self.rqc_journal_id,
            'journal_api_key_field': self.rqc_api_key,
        }
        response = self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data, follow=True)
        # Admin login template is rendered in response
        # and manager isn't.
        self.assertTemplateNotUsed(response, 'rqc_adapter/manager.html')
        self.mock_call.assert_not_called()

    def test_non_editor_non_journal_manager_can_not_edit(self):
        form_data = {
            'journal_id_field': 7,
            'journal_api_key_field': "test",
        }
        # Login Bad-User
        self.create_session_with_bad_user()
        response = self.post_manager_form(form_data)
        self.assertEqual(response.status_code, 403)

# These tests make real calls to the RQC API. In order to do so the API-Credentials need to be
# saved as environment variables. See 'has_api_credentials_env' above
# Only API-Credentials for RQC Demo-Mode journals should be used!
@skipUnless(has_api_credentials_env, "No API key found. Cannot make API call integration tests.")
class TestManagerAPIIntegration(TestManager):
    def test_api_credentials_accepted(self):
        """Form validates credentials successfully with RQC API"""
        self.create_session_with_editor()
        form_data = {
            'journal_id_field': self.rqc_journal_id,
            'journal_api_key_field': self.rqc_api_key,
        }
        response = self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data)
        # Redirect after valid post
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('rqc_adapter_manager'))
        self.assertTrue(
            RQCJournalAPICredentials.objects.filter(
                journal=self.journal_one,
                rqc_journal_id=self.rqc_journal_id,
                api_key=self.rqc_api_key
            ).exists()
        )
        messages = list(get_messages(response.wsgi_request))
        self.assertIn("RQC settings updated successfully.", [m.message for m in messages])

    def test_api_credentials_rejected(self):
        """Invalid credentials are rejected by RQC API'"""
        self.create_session_with_editor()
        form_data = {
            'journal_id_field': self.rqc_journal_id,
            'journal_api_key_field': "test",
        }
        response = self.client.post(reverse('rqc_adapter_handle_journal_settings_update'), data=form_data)
        self.assertFalse(RQCJournalAPICredentials.objects.filter(journal=self.journal_one).exists())
        # No redirect after invalid post
        self.assertNotEqual(response.status_code, 302)
        self.assertFalse(
            RQCJournalAPICredentials.objects.filter(
                journal=self.journal_one,
                rqc_journal_id=self.rqc_journal_id,
                api_key=self.rqc_api_key
            ).exists()
        )
