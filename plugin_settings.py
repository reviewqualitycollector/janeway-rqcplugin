"""
© Julius Harms, Freie Universität Berlin 2025
"""
from plugins.rqc_adapter.events import create_review_assignment_opting_decision, implicit_call_mhs_submission
from utils import plugins
from utils.logger import get_logger
from events import logic as events_logic
from events.logic import Events

from plugins.rqc_adapter.config import VERSION

PLUGIN_NAME = 'RQC Adapter Plugin'
DISPLAY_NAME = 'RQC Adapter'
DESCRIPTION = 'This plugin connects Janeway to the RQC API, allowing it to report review data for grading and inclusion in reviewers receipts.'
AUTHOR = 'Julius Harms'
SHORT_NAME = 'rqc_adapter'
MANAGER_URL = 'rqc_adapter_manager'
JANEWAY_VERSION = "1.8.0"

logger = get_logger(__name__)

# TODO add logging to CRON if CRON fails

class Rqc_adapterPlugin(plugins.Plugin):
    plugin_name = PLUGIN_NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    author = AUTHOR
    short_name = SHORT_NAME
    manager_url = MANAGER_URL

    version = VERSION
    janeway_version = JANEWAY_VERSION

    is_workflow_plugin = False

def install():
    Rqc_adapterPlugin.install()

def hook_registry():
    Rqc_adapterPlugin.hook_registry()
    return {
        'in_review_editor_actions': {
                    'module': 'plugins.rqc_adapter.hooks',
                    'function': 'render_rqc_grading_action',
        },
        'review_form_guidelines': {
            'module': 'plugins.rqc_adapter.hooks',
            'function': 'render_reviewer_opting_form',
        }
    }

def register_for_events():
    # The RQC API requires an implicit call when the editorial decision
    # for an article is changed
    events_logic.Events.register_for_event(
        Events.ON_ARTICLE_ACCEPTED,
        implicit_call_mhs_submission,
    )
    events_logic.Events.register_for_event(
        Events.ON_ARTICLE_DECLINED,
        implicit_call_mhs_submission,
    )
    events_logic.Events.register_for_event(
        Events.ON_ARTICLE_UNDECLINED,
        implicit_call_mhs_submission
    )
    events_logic.Events.register_for_event(
        Events.ON_REVISIONS_REQUESTED,
        implicit_call_mhs_submission,
    )
    events_logic.Events.register_for_event(
        Events.ON_REVIEWER_ACCEPTED,
        create_review_assignment_opting_decision
    )