from homeassistant.components.nest import *

# Imports needed for derived Nest class.
import time
from requests.compat import json

parent_setup = setup

# Override platform setup method to define and use a derived nest.Nest class.
def setup(hass, config):
    import nest
    import nest.nest as nst

    # Customize nest.Nest to:
    #   1. Add more error checking to _request().
    #   2. Add small delay between call to _put() and "busting" cache so that
    #      any changed values on server have enough time to update before next
    #      call to _get().
    class Nest(nest.Nest):
        # Override to make _bust_cache use no delay (since now the default is
        # to delay.)
        @property
        def client_version_out_of_date(self):
            if self._product_version is not None:
                self._bust_cache(delay=None)
                try:
                    return self.client_version < self._product_version
                # an error means they need to authorize anyways
                except nst.AuthorizationError:
                    return True
            return False

        # Override to add call to response.raise_for_status().
        def _request(self, verb, path="/", data=None):
            url = "%s%s" % (nst.API_URL, path)

            if data is not None:
                data = json.dumps(data)

            response = self._session.request(verb, url,
                                             allow_redirects=False,
                                             data=data)
            if response.status_code == 200:
                return response.json()

            if response.status_code == 401:
                raise nst.AuthorizationError(response)

            if response.status_code != 307:
                raise nst.APIError(response)

            redirect_url = response.headers['Location']
            response = self._session.request(verb, redirect_url,
                                             allow_redirects=False,
                                             data=data)
            # TODO check for 429 status code for too frequent access.
            # see https://developers.nest.com/documentation/cloud/data-rate-limits
            if 400 <= response.status_code < 600:
                raise nst.APIError(response)

            response.raise_for_status()
            return response.json()

        # Override to change _cache from (value, last_update) to
        # (value, expiration).
        @property
        def _status(self):
            value, expiration = self._cache

            if not value or time.time() > expiration:
                value = self._get("/")
                self._cache = (value, time.time() + self._cache_ttl)

            return value

        # Override to change _cache from (value, last_update) to
        # (value, expiration). Also add delay parameter and default
        # to enough delay to allow next get to see recently updated values.
        def _bust_cache(self, delay=7):
            if delay is None:
                self._cache = (None, 0)
            elif self._cache[0]:
                self._cache = (self._cache[0], time.time() + delay)

    # Make parent setup use our new derived Nest class.
    nest.Nest = Nest
    return parent_setup(hass, config)
