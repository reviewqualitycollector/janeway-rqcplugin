"""
© Julius Harms, Freie Universität Berlin 2025

This file is used to import urls from the core janeway modules during testing.
"""
from core import urls
from django.urls import include, re_path

urlpatterns = urls.urlpatterns + [
    re_path(r'^plugins/janeway_rqcplugin/', include('plugins.janeway_rqcplugin.urls')),
]