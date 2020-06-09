# Borrowed from https://github.com/burnhamup/galaxy-integration-indiegala/blob/master/src/http_client.py
import logging

import aiohttp
import os
from galaxy.api.errors import AuthenticationRequired
from galaxy.api.types import Cookie
from galaxy.http import create_client_session
from yarl import URL


class CookieJar(aiohttp.CookieJar):
    # Inspired by https://github.com/TouwaStar/Galaxy_Plugin_Bethesda/blob/master/betty/http_client.py
    def __init__(self):
        super().__init__()
        self._cookies_updated_callback = None

    def set_cookies_updated_callback(self, callback):
        self._cookies_updated_callback = callback

    def update_cookies(self, cookies, url=URL()):
        super().update_cookies(cookies, url)
        if cookies and self._cookies_updated_callback:
            all_cookies = {cookie.key: cookie.value for cookie in self}
            self._cookies_updated_callback(all_cookies)


class HTTPClient(object):
    """
    Intended to store and track cookies and update them on each request
    """
    def __init__(self, store_credentials):
        self.cookieJar = CookieJar()
        self.cookieJar.set_cookies_updated_callback(store_credentials)
        self.session = create_client_session(cookie_jar=self.cookieJar)

    async def get(self, url):
        """
        returns the url and updates the cookies
        :param url:
        :return:
        """
        logging.debug('Calling HTTPClient.get with %s', url)
        response = await self.session.get(url)
        parsed = await response.json()
        return parsed

    def update_cookies(self, cookies):
        self.cookieJar.update_cookies(cookies)

    def get_next_step_cookies(self):
        return [Cookie(cookie.key, cookie.value) for cookie in self.cookieJar]

    async def close(self):
        await self.session.close()
