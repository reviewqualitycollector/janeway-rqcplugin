"""
© Julius Harms, Freie Universität Berlin 2025
"""

from plugins.janeway_rqcplugin import views
from django.urls import re_path
urlpatterns = [
    re_path(r'^manager/$', views.manager, name='janeway_rqcplugin_manager'),
    re_path(r'^manager/handle_journal_settings_update$', views.handle_journal_settings_update, name='janeway_rqcplugin_handle_journal_settings_update'),
    re_path(r'^articles/(?P<article_id>\d+)/submit$', views.submit_article_for_grading, name='janeway_rqcplugin_submit_article_for_grading'),
    re_path(r'^set_reviewer_opting_status/(?P<assignment_id>\d+)$', views.set_reviewer_opting_status, name='janeway_rqcplugin_set_reviewer_opting_status'),
]
