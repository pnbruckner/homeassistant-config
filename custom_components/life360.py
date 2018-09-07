"""
Low level python module for accessing Life360 REST API.

For more details about this platform, please refer to
https://github.com/pnbruckner/homeassistant-config#life360py--device_trackerlife360py
"""

import requests
import json
import os
import stat

__version__ = '1.0.0'

_BASE_URL = 'https://api.life360.com/v3/'
_TOKEN_URL = _BASE_URL + 'oauth2/token.json'
_CIRCLES_URL = _BASE_URL + 'circles.json'
_CIRCLE_URL = _BASE_URL + 'circles/{}'

class life360(object):

    def __init__(self, auth_info_callback, timeout=None,
                 authorization_cache_file=None):
        self._auth_info_callback = auth_info_callback
        self._timeout = timeout
        self._authorization_cache_file = authorization_cache_file
        self._authorization = None
        self._session = requests.Session()
        self._session.headers.update(
            {'Accept': 'application/json', 'cache-control': 'no-cache'})

    def _load_authorization(self):
        if self._authorization_cache_file and os.path.exists(
                self._authorization_cache_file):
            with open(self._authorization_cache_file, 'r') as f:
                self._authorization = f.read()
            return True
        return False

    def _save_authorization(self):
        if self._authorization_cache_file:
            try:
                os.remove(self._authorization_cache_file)
            except:
                pass
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            mode = stat.S_IRUSR | stat.S_IWUSR
            umask = 0o777 ^ mode
            umask_orig = os.umask(umask)
            try:
                with open(os.open(
                        self._authorization_cache_file, flags, mode), 'w') as f:
                    f.write(self._authorization)
            finally:
                os.umask(umask_orig)

    def _authenticate(self):
        """Use authorization token, username & password to get access token."""
        try:
            auth_token, username, password = self._auth_info_callback()
        except ValueError as exc:
            raise ValueError(
                'auth_info_callback must return tuple of: '
                'authorization token, username, password') from exc

        data = {
            'grant_type': 'password',
            'username': username,
            'password': password,
        }
        resp = self._session.post(_TOKEN_URL, data=data, timeout=self._timeout,
            headers={'Authorization': 'Basic ' + auth_token})

        if not resp.ok:
            # If it didn't work, try to return a useful error message.
            try:
                err_msg = json.loads(resp.text)['errorMessage']
            except:
                resp.raise_for_status()
                raise ValueError('Unexpected response to {}: {}: {}'.format(
                    _TOKEN_URL, resp.status_code, resp.text))
            raise ValueError(err_msg)

        resp = resp.json()
        self._authorization = ' '.join([resp['token_type'],
                                        resp['access_token']])
        self._save_authorization()

    def _authorize(self):
        if not self._authorization:
            if not self._load_authorization():
                self._authenticate()

    def _get(self, url):
        self._authorize()
        resp = self._session.get(url, timeout=self._timeout,
            headers={'Authorization': self._authorization})
        # If authorization error (401), try regenerating authorization
        # and sending again.
        if resp.status_code == 401:
            self._authenticate()
            resp.request.headers['Authorization'] = self._authorization
            resp = self._session.send(resp.request)

        resp.raise_for_status()
        return resp.json()

    def get_circles(self):
        return self._get(_CIRCLES_URL)['circles']

    def get_circle(self, circle_id):
        return self._get(_CIRCLE_URL.format(circle_id))
