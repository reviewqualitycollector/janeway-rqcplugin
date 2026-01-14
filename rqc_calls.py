"""
© Julius Harms, Freie Universität Berlin 2025

This file handles the immediate logic of calling the RQC API.
Exceptions while calling the API get handled here and passed down via the result dictionary
in the call_rqc_api function.
"""

import json
from enum import IntEnum

import requests
from requests import RequestException

from utils.logger import get_logger
from utils.models import Version

from plugins.janeway_rqcplugin.models import RQCCall, RQCReviewerOptingDecisionForReviewAssignment
from plugins.janeway_rqcplugin.utils import convert_date_to_rqc_format
from plugins.janeway_rqcplugin.config import API_VERSION, API_BASE_URL, REQUEST_TIMEOUT
from plugins.janeway_rqcplugin.config import VERSION

logger = get_logger(__name__)

class RQCErrorCodes(IntEnum):
    CONNECTION_ERROR = -1
    TIMEOUT = -2
    REQUEST_ERROR = -3
    UNKNOWN_ERROR = -4

def call_mhs_apikeycheck(journal_id: int, api_key: str) -> dict:
    """
    Verify API key with the RQC service.
    :param journal_id: str: The journal Id as issued by RQC
    :param api_key: str: The API key to validate
    :return:int: dict: Response data dictionary. See call_rqc_api for details.
    """
    url = f'{API_BASE_URL}/mhs_apikeycheck/{journal_id}'
    return call_rqc_api(url, api_key)

def call_mhs_submission(journal_id: int, api_key: str, submission_id, post_data: str, article=None) -> dict:
    """
    Calls the mhs_submission endpoint of the RQC API.
    :param journal_id: str: The journal Id as issued by RQC
    :param api_key: str: The API key to validate
    :param submission_id: str: id of the submission (article)
    :param post_data: str: data to send in the request
    :param article: Article object
    :return: dict: Response data dictionary. See call_rqc_api for details.
    """
    url = f'{API_BASE_URL}/mhs_submission/{journal_id}/{submission_id}'
    return call_rqc_api(url , api_key, use_post=True, post_data=post_data, article=article)

def log_call_result(result: dict):
    if result['success']:
        logger.info(f'RQC API call succeeded. More information: {result}')
    else:
        logger.info(f'RQC API call failed. More information: {result}')

def call_rqc_api(url: str, api_key: str, use_post=False, post_data=None, article=None) -> dict:
    """Calls the RQC API. Calling endpoint depends on use_post.
    :param url: str: URL to call
    :param api_key: str: API key
    :param use_post: bool: Whether to use post request or not
    :param post_data: str: Post data
    :param article: str: Article object
    :return: dict: Response data and error message dictionary."""
    result = {
        'success': False, # Boolean if satus code is 200 or 303. Because RQC responds with 303
        # in the case of a successful (accepted) call that was triggered by an interactive user
        'http_status_code': None,
        # Contains http status code or RQCErrorCode defined above - Integer
        'message': None, # Contains either a message by RQC to the user if present or otherwise information
        # that can help users.
        'redirect_target': None, #Set if the RQC response contains a redirect target. None otherwise.
    }
    try:
        try:
            current_version = Version.objects.all().order_by('-number').first()
            if not current_version:
                raise ValueError('No version information available')
        except Exception as db_error:
            raise ValueError(f"Error retrieving version information: {db_error}")

        headers = {
            'X-Rqc-Api-Version': API_VERSION,
            'X-Rqc-Mhs-Version': f'Janeway {current_version.number}',
            'X-Rqc-Mhs-Adapter': f'RQC plugin {VERSION} https://github.com/JuliusHarms/janeway-rqcplugin',
            'X-Rqc-Time': convert_date_to_rqc_format(),
            'Authorization': f'Bearer {api_key}',
        }
        logger.debug("POST data to RQC %s:\n%s", url, json.dumps(post_data, indent=2, ensure_ascii=False))
        if use_post:
            headers['Content-Type'] = 'application/json'
            response = requests.post(
                url,
                json = post_data,
                headers = headers,
                timeout = REQUEST_TIMEOUT,
                allow_redirects = False,
            )
        else:
            response = requests.get(
                url,
                headers = headers,
                timeout = REQUEST_TIMEOUT
            )
        result['http_status_code'] = response.status_code
        result['success'] = response.ok

        if response.ok:
            logger.info(f'Request to RQC succeeded with status code: {response.status_code}')
        else:
            logger.debug(f'Request to RQC failed with status code: {response.status_code}')

        if response.status_code in (200, 303) and use_post:
            RQCCall.objects.get_or_create(article=article, defaults = {'editor_assignments': post_data['edassgmt_set']})
            # The Reviews that are sent to RQC are saved, in order to handle
            # the case where a reviewer accepts a review assignment, then an RQC call is made and then
            # the reviewer declines the review assignment. In that case according to the API description
            # the review data has to be resent on subsequent calls despite the fact that the reviewer
            # has since then declined the review assignment.
            RQCReviewerOptingDecisionForReviewAssignment.objects.filter(
                review_assignment__article=article, review_assignment__date_declined__isnull=True
            ).update(sent_to_rqc=True)
        if response.status_code == 200 and use_post:
            log_call_result(result)
            return result
        # Otherwise try to parse the body
        else:
            try:
                response_data = response.json()
                try:
                    if 'user_message' in response_data:
                        result['message'] = response_data['user_message']
                    elif "error" in response_data:
                        result['message'] = response_data['error']
                    elif not response.status_code in (200, 303):
                        error_string = ""
                        if isinstance(response_data, dict):
                            errors = []
                            for field, msgs in response_data.items():
                                if isinstance(msgs, list):
                                    for msg in msgs:
                                        errors.append(f"{field}: {msg}")
                                else:
                                    errors.append(f"{field}: {msgs}")
                            error_string = "; ".join(errors)
                        result['message'] = f'Request failed: {response.reason} ({error_string})'
                    if result['http_status_code'] == 303:
                        result['redirect_target'] = response_data.get('redirect_target')
                        result['success'] = True
                except ValueError:
                    result[
                        "message"] = f'Request failed and no error message was provided. Request status: {response.reason}'
            except json.decoder.JSONDecodeError:
                result["message"] = f'Request succeeded but response body was malformed. Request status: {response.reason}'
            log_call_result(result)
            return result
    except requests.Timeout:
        result['http_status_code'] = RQCErrorCodes.TIMEOUT
        result['message'] = 'API request timed out. Please try again later.'
    except requests.ConnectionError:
        result['http_status_code'] = RQCErrorCodes.CONNECTION_ERROR
        result['message'] = 'Unable to connect to API service. Please try again later.'
    except RequestException as e:
        result['http_status_code'] = RQCErrorCodes.REQUEST_ERROR
        result['message'] = f'API service returned an invalid response: {str(e)}'
    except Exception as e:
        result['http_status_code'] = RQCErrorCodes.UNKNOWN_ERROR
        result['message'] = f'Unexpected error: {str(e)}'
    log_call_result(result)
    return result