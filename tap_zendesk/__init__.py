#!/usr/bin/env python3
import json
import sys

import requests
import singer
from requests.adapters import HTTPAdapter, Retry
from singer import metadata
from zenpy import Zenpy

from tap_zendesk import metrics as zendesk_metrics
from tap_zendesk.discover import discover_streams
from tap_zendesk.streams import STREAMS
from tap_zendesk.sync import sync_stream

LOGGER = singer.get_logger()

REQUIRED_CONFIG_KEYS = [
    "start_date",
    "subdomain",
]

# default authentication
OAUTH_CONFIG_KEYS = [
    "access_token",
]

# email + api_token authentication
API_TOKEN_CONFIG_KEYS = [
    "email",
    "api_token",
]


def do_discover(client):
    LOGGER.info("Starting discover")
    catalog = {"streams": discover_streams(client)}
    json.dump(catalog, sys.stdout, indent=2)
    LOGGER.info("Finished discover")


def do_sync(client, catalog, state, config):
    for stream in catalog.streams:
        STREAMS[stream.tap_stream_id].stream = stream

    for stream in catalog.streams:
        stream_name = stream.tap_stream_id
        mdata = metadata.to_map(stream.metadata)

        key_properties = metadata.get(mdata, (), 'table-key-properties')
        singer.write_schema(stream_name, stream.schema.to_dict(), key_properties)

        LOGGER.info("%s: Starting sync", stream_name)
        instance = STREAMS[stream_name](client, config)
        sync_stream(state, config.get('start_date'), instance)
        singer.write_state(state)


def oauth_auth(args):
    if not set(OAUTH_CONFIG_KEYS).issubset(args.config.keys()):
        LOGGER.debug("OAuth authentication unavailable.")
        return None

    LOGGER.info("Using OAuth authentication.")
    return {
        "subdomain": args.config['subdomain'],
        "oauth_token": args.config['access_token'],
    }


def api_token_auth(args):
    if not set(API_TOKEN_CONFIG_KEYS).issubset(args.config.keys()):
        LOGGER.debug("API Token authentication unavailable.")
        return None

    LOGGER.info("Using API Token authentication.")
    return {
        "subdomain": args.config['subdomain'],
        "email": args.config['email'],
        "token": args.config['api_token']
    }


def get_session(config):
    """ Add partner information to requests Session object if specified in the config. """
    if not all(k in config for k in ["marketplace_name",
                                     "marketplace_organization_id",
                                     "marketplace_app_id"]):
        return None
    session = requests.Session()
    # Using Zenpy's default adapter args, following the method outlined here:
    # https://github.com/facetoe/zenpy/blob/master/docs/zenpy.rst#usage
    session.mount("https://", HTTPAdapter(**Zenpy.http_adapter_kwargs()))
    session.headers["X-Zendesk-Marketplace-Name"] = config.get("marketplace_name", "")
    session.headers["X-Zendesk-Marketplace-Organization-Id"] = str(config.get("marketplace_organization_id", ""))
    session.headers["X-Zendesk-Marketplace-App-Id"] = str(config.get("marketplace_app_id", ""))
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504, 520])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session


@singer.utils.handle_top_exception(LOGGER)
def main():
    parsed_args = singer.utils.parse_args(REQUIRED_CONFIG_KEYS)

    # OAuth has precedence
    creds = oauth_auth(parsed_args) or api_token_auth(parsed_args)
    session = get_session(parsed_args.config)

    client = Zenpy(session=session, **creds)

    if not client:
        LOGGER.error("""No suitable authentication keys provided.""")

    if parsed_args.discover:
        do_discover(client)
    elif parsed_args.catalog:
        state = parsed_args.state
        do_sync(client, parsed_args.catalog, state, parsed_args.config)


if __name__ == '__main__':
    main()
