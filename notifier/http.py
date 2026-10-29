"""Shared HTTP helper so every request gets the same timeout and retry."""

import logging

import requests

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15
HEADERS = {"User-Agent": "neuro-job-notifier"}


def get_json(url: str):
    """GET a URL and return the parsed JSON. Retries once on a network error or
    a 5xx response, since job board APIs sometimes have a brief hiccup."""
    for attempt in (1, 2):
        try:
            # requests applies the timeout to connecting and to each read from
            # the socket, not to the whole download, so big files still work.
            response = requests.get(url, timeout=TIMEOUT_SECONDS, headers=HEADERS)
            if response.status_code < 500:
                response.raise_for_status()  # 4xx: retrying won't help
                return response.json()
            error = requests.HTTPError(f"{response.status_code} from {url}")
        except (requests.ConnectionError, requests.Timeout) as exc:
            error = exc
        if attempt == 1:
            log.info("retrying %s after: %s", url, error)
    raise error
