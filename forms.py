"""
© Julius Harms, Freie Universität Berlin 2025

The forms used by the plugin are defined here.
"""
from django import forms
from django.core.validators import RegexValidator

from plugins.janeway_rqcplugin.models import RQCReviewerOptingDecision
from plugins.janeway_rqcplugin.rqc_calls import call_mhs_apikeycheck

class RqcSettingsForm(forms.Form):
    journal_id_field = forms.IntegerField(error_messages={'invalid': 'Journal ID must be a number'}, label='RQC journal ID',
                                          help_text='An integer that is supplied when you register a journal at RQC.'
                                                    ' You may need to ask your publisher to create one at'
                                                    ' <a href="https://reviewqualitycollector.org" target="_blank" rel="noopener noreferrer">reviewqualitycollector.org</a> '
                                                    'or use RQC\'s Demo mode to try it out yourself.')
    journal_api_key_field = forms.CharField(
        max_length=64, min_length=1,
        widget=forms.PasswordInput,
        validators=[
            RegexValidator(
                regex='^[0-9A-Za-z]+$',
                message='The API key must only contain alphanumeric characters.')], label='RQC secret journal API key',
                help_text='An alphanumeric string created by RQC upon request.' 
                          ' This value is secret and is used for authentication.'            
                          ' Ask your publisher to tell you yours or use RQC\'s Demo mode and create one yourself.')

    # Validate submitted journal_id and api_key together
    # Since validation depends on both, and we need to make sure only valid data is used
    # to make API calls.
    def clean(self):
        cleaned_data = super().clean()
        journal_id = cleaned_data.get('journal_id_field')
        api_key = cleaned_data.get('journal_api_key_field')
        if journal_id and api_key:
            try:
                call_result = call_mhs_apikeycheck(journal_id, api_key)
            # Generic Exception
            # Generally Exceptions are handled in rqc_calls.py by propagating appropriate error messages via call_results[message].
            # If this doesn't happen we can only transmit a generic error message.
            except Exception as e:
                raise forms.ValidationError('Unable to verify API credentials.', code='verification_failed_generic', params={'exception': e})
            if not call_result["success"]:
                http_status_code = call_result.get('http_status_code')
                error_msg = call_result.get('message')
                message = ''
                if error_msg:
                    message += f'Details: {error_msg}'
                if http_status_code:
                    http_status_code = str(http_status_code)
                    message = f'HTTP status code: {http_status_code}. {message}'
                error_dict = {'http_status_code': http_status_code, 'error_msg': call_result['message']}
                raise forms.ValidationError(message, code=http_status_code, params=error_dict)
        return cleaned_data

class ReviewerOptingForm(forms.Form):
    status_selection_field = forms.ChoiceField(choices=[
        (RQCReviewerOptingDecision.OptingChoices.OPT_IN, "Yes, take part in RQC"),
         (RQCReviewerOptingDecision.OptingChoices.OPT_OUT, "No, opt out from RQC")])
