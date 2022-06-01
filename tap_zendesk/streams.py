import datetime
import json
import os
import time

import pytz
import singer
import zenpy
from singer import metadata
from singer import utils
from zenpy.lib.exception import RecordNotFoundException

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

LOGGER = singer.get_logger()
KEY_PROPERTIES = ['id']

CUSTOM_TYPES = {
    'text': 'string',
    'textarea': 'string',
    'date': 'string',
    'regexp': 'string',
    'dropdown': 'string',
    'integer': 'integer',
    'decimal': 'number',
    'checkbox': 'boolean',
}

DEFAULT_SEARCH_WINDOW_SIZE = (60 * 60 * 24) * 30  # defined in seconds, default to a month (30 days)


def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)


def process_custom_field(field):
    """ Take a custom field description and return a schema for it. """
    zendesk_type = field.type
    json_type = CUSTOM_TYPES.get(zendesk_type)
    if json_type is None:
        raise Exception("Discovered unsupported type for custom field {} (key: {}): {}"
                        .format(field.title,
                                field.key,
                                zendesk_type))
    field_schema = {'type': [
        json_type,
        'null'
    ]}

    if zendesk_type == 'date':
        field_schema['format'] = 'datetime'
    if zendesk_type == 'dropdown':
        field_schema['enum'] = [o['value'] for o in field.custom_field_options]

    return field_schema


class Stream:
    name = None
    replication_method = None
    replication_key = None
    key_properties = KEY_PROPERTIES
    stream = None

    def __init__(self, client=None, config=None):
        self.client = client
        self.config = config

    def get_bookmark(self, state):
        return utils.strptime_with_tz(singer.get_bookmark(state, self.name, self.replication_key))

    def update_bookmark(self, state, value):
        current_bookmark = self.get_bookmark(state)
        if value and utils.strptime_with_tz(value) > current_bookmark:
            value = utils.strptime_with_tz(value) + datetime.timedelta(seconds=1)
            value = value.strftime(DATETIME_FORMAT)
            singer.write_bookmark(state, self.name, self.replication_key, value)

    def load_schema(self):
        schema_file = "schemas/{}.json".format(self.name)
        with open(get_abs_path(schema_file)) as f:
            schema = json.load(f)
        return self._add_custom_fields(schema)

    def _add_custom_fields(self, schema):  # pylint: disable=no-self-use
        return schema

    def load_metadata(self):
        schema = self.load_schema()
        mdata = metadata.new()

        mdata = metadata.write(mdata, (), 'table-key-properties', self.key_properties)
        mdata = metadata.write(mdata, (), 'forced-replication-method', self.replication_method)

        if self.replication_key:
            mdata = metadata.write(mdata, (), 'valid-replication-keys', [self.replication_key])

        for field_name in schema['properties'].keys():
            if field_name in self.key_properties or field_name == self.replication_key:
                mdata = metadata.write(mdata, ('properties', field_name), 'inclusion', 'automatic')
            else:
                mdata = metadata.write(mdata, ('properties', field_name), 'inclusion', 'available')

        return metadata.to_list(mdata)

    def is_selected(self):
        return self.stream is not None


def raise_or_log_zenpy_apiexception(schema, stream, e):
    # There are multiple tiers of Zendesk accounts. Some of them have
    # access to `custom_fields` and some do not. This is the specific
    # error that appears to be return from the API call in the event that
    # it doesn't have access.
    if not isinstance(e, zenpy.lib.exception.APIException):
        raise ValueError("Called with a bad exception type") from e
    if json.loads(e.args[0])['error']['message'] == "You do not have access to this page. Please contact the account owner of this help desk for further help.":
        LOGGER.warning("The account credentials supplied do not have access to `%s` custom fields.",
                       stream)
        return schema
    else:
        raise e


class Organizations(Stream):
    name = "organizations"
    replication_method = "INCREMENTAL"
    replication_key = "updated_at"

    def _add_custom_fields(self, schema):
        endpoint = self.client.organizations.endpoint
        # NB: Zenpy doesn't have a public endpoint for this at time of writing
        #     Calling into underlying query method to grab all fields
        try:
            field_gen = self.client.organizations._query_zendesk(endpoint.organization_fields,  # pylint: disable=protected-access
                                                                 'organization_field')
        except zenpy.lib.exception.APIException as e:
            return raise_or_log_zenpy_apiexception(schema, self.name, e)
        schema['properties']['organization_fields']['properties'] = {}
        for field in field_gen:
            schema['properties']['organization_fields']['properties'][field.key] = process_custom_field(field)

        return schema

    def sync(self, state):
        bookmark = self.get_bookmark(state)
        organizations = self.client.organizations.incremental(start_time=bookmark)
        for organization in organizations:
            bookmark = datetime.datetime.strptime(organization.updated_at, DATETIME_FORMAT) + datetime.timedelta(seconds=1)
            self.update_bookmark(state, bookmark.strftime(DATETIME_FORMAT))
            yield self.stream, organization


class Users(Stream):
    name = "users"
    replication_method = "INCREMENTAL"
    replication_key = "updated_at"

    def _add_custom_fields(self, schema):
        try:
            field_gen = self.client.user_fields()
        except zenpy.lib.exception.APIException as e:
            return raise_or_log_zenpy_apiexception(schema, self.name, e)
        schema['properties']['user_fields']['properties'] = {}
        for field in field_gen:
            schema['properties']['user_fields']['properties'][field.key] = process_custom_field(field)

        return schema

    def sync(self, state):
        original_search_window_size = int(self.config.get('search_window_size', DEFAULT_SEARCH_WINDOW_SIZE))
        search_window_size = original_search_window_size
        bookmark = self.get_bookmark(state)
        start = bookmark - datetime.timedelta(seconds=1)
        end = start + datetime.timedelta(seconds=search_window_size)
        sync_end = singer.utils.now() - datetime.timedelta(minutes=1)
        parsed_sync_end = singer.strftime(sync_end, DATETIME_FORMAT)

        # ASSUMPTION: updated_at value always comes back in utc
        num_retries = 0
        while start < sync_end:
            parsed_start = singer.strftime(start, DATETIME_FORMAT)
            parsed_end = min(singer.strftime(end, DATETIME_FORMAT), parsed_sync_end)
            LOGGER.info("Querying for users between %s and %s", parsed_start, parsed_end)
            users = self.client.search("", updated_after=parsed_start, updated_before=parsed_end, type="user")

            # NB: Zendesk will return an error on the 1001st record, so we
            # need to check total response size before iterating
            # See: https://develop.zendesk.com/hc/en-us/articles/360022563994--BREAKING-New-Search-API-Result-Limits
            if users.count > 1000:
                if search_window_size > 1:
                    search_window_size = search_window_size // 2
                    end = start + datetime.timedelta(seconds=search_window_size)
                    LOGGER.info("users - Detected Search API response size too large. Cutting search window in half to %s seconds.", search_window_size)
                    continue

                raise Exception("users - Unable to get all users within minimum window of a single second ({}), found {} users within this timestamp. Zendesk can only provide a maximum of 1000 users per request. See: https://develop.zendesk.com/hc/en-us/articles/360022563994--BREAKING-New-Search-API-Result-Limits".format(parsed_start, users.count))

            # Consume the records to account for dates lower than window start
            users = [user for user in users]  # pylint: disable=unnecessary-comprehension

            if not all(parsed_start <= user.updated_at for user in users):
                # Only retry up to 30 minutes (60 attempts at 30 seconds each)
                if num_retries < 60:
                    LOGGER.info("users - Record found before date window start. Waiting 30 seconds, then retrying window for consistency. (Retry #%s)", num_retries + 1)
                    time.sleep(30)
                    num_retries += 1
                    continue
                raise AssertionError("users - Record found before date window start and did not resolve after 30 minutes of retrying. Details: window start ({}) is not less than or equal to updated_at value(s) {}".format(
                    parsed_start, [str(user.updated_at) for user in users if user.updated_at < parsed_start]))

            # If we make it here, all quality checks have passed. Reset retry count.
            num_retries = 0
            for user in users:
                if parsed_start <= user.updated_at <= parsed_end:
                    yield self.stream, user
            self.update_bookmark(state, parsed_end)

            # Assumes that the for loop got everything
            singer.write_state(state)
            if search_window_size <= original_search_window_size // 2:
                search_window_size = search_window_size * 2
                LOGGER.info("Successfully requested records. Doubling search window to %s seconds", search_window_size)
            start = end - datetime.timedelta(seconds=1)
            end = start + datetime.timedelta(seconds=search_window_size)


class Tickets(Stream):
    name = "tickets"
    replication_method = "INCREMENTAL"
    replication_key = "generated_timestamp"

    def push_ticket_child(self, state, ticket, child):
        child = child.to_dict()
        generated_timestamp = ticket["generated_timestamp"]
        child["ticket_generated_timestamp"] = generated_timestamp
        generated_timestamp_dt = datetime.datetime.utcfromtimestamp(generated_timestamp).replace(tzinfo=pytz.UTC) + datetime.timedelta(seconds=1)
        self.update_bookmark(state, utils.strftime(generated_timestamp_dt))
        yield self.stream, child

    def sync(self, state):
        bookmark = self.get_bookmark(state)
        ids = []
        tickets = self.client.tickets.incremental(start_time=bookmark)

        for ticket in tickets:
            generated_timestamp_dt = datetime.datetime.utcfromtimestamp(ticket.generated_timestamp).replace(tzinfo=pytz.UTC) + datetime.timedelta(seconds=1)
            self.update_bookmark(state, utils.strftime(generated_timestamp_dt))
            ticket = ticket.to_dict()
            if ticket["id"] not in ids:
                # avoid duplicate records because of zenpy package pagination issue
                ids.append(ticket["id"])
                ticket.pop('fields')  # NB: Fields is a duplicate of custom_fields, remove before emitting
                yield self.stream, ticket


class TicketAudits(Tickets):
    name = "ticket_audits"
    replication_method = "INCREMENTAL"
    replication_key = "ticket_generated_timestamp"
    count = 0

    def sync(self, state):
        bookmark = self.get_bookmark(state)
        tickets = self.client.tickets.incremental(start_time=bookmark)
        ids = []
        ticket_count = 0
        for ticket in tickets:
            if ticket_count % 100 == 0:
                LOGGER.info("Pushed audit records for %s tickets", ticket_count)
            ticket = ticket.to_dict()
            if ticket["status"] != "deleted" and ticket["id"] not in ids:  # Only audits of undeleted tickets can be retrieved.
                ticket_audits = self.client.tickets.audits(ticket=ticket["id"])
                ids.append(ticket["id"])
                for ticket_audit in ticket_audits:
                    yield from self.push_ticket_child(state, ticket, ticket_audit)
            ticket_count += 1


class TicketMetrics(Tickets):
    name = "ticket_metrics"
    replication_method = "INCREMENTAL"
    replication_key = "ticket_generated_timestamp"

    def sync(self, state):
        bookmark = self.get_bookmark(state)
        tickets = self.client.tickets.incremental(start_time=bookmark)
        ids = []
        ticket_count = 0
        for ticket in tickets:
            if ticket_count % 100 == 0:
                LOGGER.info("Pushed metrics records for %s tickets", ticket_count)
            ticket = ticket.to_dict()
            if ticket["id"] not in ids:
                ids.append(ticket["id"])
                try:
                    ticket_metric = self.client.tickets.metrics(ticket=ticket["id"])
                    yield from self.push_ticket_child(state, ticket, ticket_metric)
                except Exception as e:
                    LOGGER.warning("Ticket not found")
            ticket_count += 1


class TicketComments(Tickets):
    name = "ticket_comments"
    replication_method = "INCREMENTAL"
    replication_key = "ticket_generated_timestamp"

    def sync(self, state):
        bookmark = self.get_bookmark(state)
        tickets = self.client.tickets.incremental(start_time=bookmark)
        ids = []
        ticket_count = 0
        for ticket in tickets:
            if ticket_count % 100 == 0:
                LOGGER.info("Pushed comments records for %s tickets", ticket_count)
            ticket = ticket.to_dict()
            if ticket["status"] != "deleted" and ticket["id"] not in ids:  # Only comments of undeleted tickets can be retrieved.
                ticket_comments = self.client.tickets.comments(ticket=ticket["id"])
                ids.append(ticket["id"])
                for ticket_comment in ticket_comments:
                    yield from self.push_ticket_child(state, ticket, ticket_comment)
            ticket_count += 1

class SatisfactionRatings(Stream):
    name = "satisfaction_ratings"
    replication_method = "INCREMENTAL"
    replication_key = "updated_at"

    def sync(self, state):
        bookmark = self.get_bookmark(state)
        original_search_window_size = int(self.config.get('search_window_size', DEFAULT_SEARCH_WINDOW_SIZE))
        search_window_size = original_search_window_size
        start = bookmark
        end = start + datetime.timedelta(seconds=search_window_size)
        sync_end = singer.utils.now() - datetime.timedelta(minutes=1)
        epoch_sync_end = int(sync_end.strftime('%s'))
        parsed_sync_end = singer.strftime(sync_end, DATETIME_FORMAT)

        while start < sync_end:
            epoch_start = int(start.strftime('%s'))
            parsed_start = singer.strftime(start, DATETIME_FORMAT)
            epoch_end = int(end.strftime('%s'))
            parsed_end = singer.strftime(end, DATETIME_FORMAT)

            LOGGER.info("Querying for satisfaction ratings between %s and %s", parsed_start, min(parsed_end, parsed_sync_end))
            satisfaction_ratings = self.client.satisfaction_ratings(start_time=epoch_start,
                                                                    end_time=min(epoch_end, epoch_sync_end))
            # NB: We've observed that the tap can sync 50k records in ~15
            # minutes, due to this, the tap will adjust the time range
            # dynamically to ensure bookmarks are able to be written in
            # cases of high volume.
            if satisfaction_ratings.count > 50000:
                search_window_size = search_window_size // 2
                end = start + datetime.timedelta(seconds=search_window_size)
                LOGGER.info("satisfaction_ratings - Detected Search API response size for this window is too large (> 50k). Cutting search window in half to %s seconds.", search_window_size)
                continue
            for satisfaction_rating in satisfaction_ratings:
                assert parsed_start <= satisfaction_rating.updated_at, "satisfaction_ratings - Record found before date window start. Details: window start ({}) is not less than or equal to updated_at ({})".format(parsed_start, satisfaction_rating.updated_at)
                if bookmark < utils.strptime_with_tz(satisfaction_rating.updated_at) <= end:
                    # NB: We don't trust that the records come back ordered by
                    # updated_at (we've observed out-of-order records),
                    # so we can't save state until we've seen all records
                    self.update_bookmark(state, satisfaction_rating.updated_at)
                if parsed_start <= satisfaction_rating.updated_at <= parsed_end:
                    yield (self.stream, satisfaction_rating)
            if search_window_size <= original_search_window_size // 2:
                search_window_size = search_window_size * 2
                LOGGER.info("Successfully requested records. Doubling search window to %s seconds", search_window_size)
            singer.write_state(state)

            start = end - datetime.timedelta(seconds=1)
            end = start + datetime.timedelta(seconds=search_window_size)


class Groups(Stream):
    name = "groups"
    replication_method = "INCREMENTAL"
    replication_key = "updated_at"

    def sync(self, state):
        bookmark = self.get_bookmark(state)

        groups = self.client.groups()
        for group in groups:
            if utils.strptime_with_tz(group.updated_at) >= bookmark:
                # NB: We don't trust that the records come back ordered by
                # updated_at (we've observed out-of-order records),
                # so we can't save state until we've seen all records
                self.update_bookmark(state, group.updated_at)
                yield self.stream, group


class Macros(Stream):
    name = "macros"
    replication_method = "INCREMENTAL"
    replication_key = "updated_at"

    def sync(self, state):
        bookmark = self.get_bookmark(state)

        macros = self.client.macros()
        for macro in macros:
            if utils.strptime_with_tz(macro.updated_at) >= bookmark:
                # NB: We don't trust that the records come back ordered by
                # updated_at (we've observed out-of-order records),
                # so we can't save state until we've seen all records
                self.update_bookmark(state, macro.updated_at)
                yield (self.stream, macro)


class Tags(Stream):
    name = "tags"
    replication_method = "FULL_TABLE"
    key_properties = ["name"]

    def sync(self, state):  # pylint: disable=unused-argument
        # NB: Setting page to force it to paginate all tags, instead of just the
        #     top 100 popular tags
        tags = self.client.tags(page=1)
        for tag in tags:
            yield (self.stream, tag)


class TicketFields(Stream):
    name = "ticket_fields"
    replication_method = "INCREMENTAL"
    replication_key = "updated_at"

    def sync(self, state):
        bookmark = self.get_bookmark(state)

        fields = self.client.ticket_fields()
        for field in fields:
            if utils.strptime_with_tz(field.updated_at) >= bookmark:
                # NB: We don't trust that the records come back ordered by
                # updated_at (we've observed out-of-order records),
                # so we can't save state until we've seen all records
                self.update_bookmark(state, field.updated_at)
                yield (self.stream, field)


class TicketForms(Stream):
    name = "ticket_forms"
    replication_method = "INCREMENTAL"
    replication_key = "updated_at"

    def sync(self, state):
        bookmark = self.get_bookmark(state)

        forms = self.client.ticket_forms()
        for form in forms:
            if utils.strptime_with_tz(form.updated_at) >= bookmark:
                # NB: We don't trust that the records come back ordered by
                # updated_at (we've observed out-of-order records),
                # so we can't save state until we've seen all records
                self.update_bookmark(state, form.updated_at)
                yield (self.stream, form)


class GroupMemberships(Stream):
    name = "group_memberships"
    replication_method = "INCREMENTAL"
    replication_key = "updated_at"

    def sync(self, state):
        bookmark = self.get_bookmark(state)

        memberships = self.client.group_memberships()
        for membership in memberships:
            # some group memberships come back without an updated_at
            if membership.updated_at:
                if utils.strptime_with_tz(membership.updated_at) >= bookmark:
                    # NB: We don't trust that the records come back ordered by
                    # updated_at (we've observed out-of-order records),
                    # so we can't save state until we've seen all records
                    self.update_bookmark(state, membership.updated_at)
                    yield (self.stream, membership)
            else:
                if membership.id:
                    LOGGER.info('group_membership record with id: ' + str(membership.id) +
                                ' does not have an updated_at field so it will be syncd...')
                    yield (self.stream, membership)
                else:
                    LOGGER.info('Received group_membership record with no id or updated_at, skipping...')


class SLAPolicies(Stream):
    name = "sla_policies"
    replication_method = "FULL_TABLE"

    def sync(self, state):  # pylint: disable=unused-argument
        for policy in self.client.sla_policies():
            yield (self.stream, policy)


STREAMS = {
    "tickets": Tickets,
    "groups": Groups,
    "users": Users,
    "organizations": Organizations,
    "ticket_audits": TicketAudits,
    "ticket_comments": TicketComments,
    "ticket_fields": TicketFields,
    "ticket_forms": TicketForms,
    "group_memberships": GroupMemberships,
    "macros": Macros,
    "satisfaction_ratings": SatisfactionRatings,
    "tags": Tags,
    "ticket_metrics": TicketMetrics,
    "sla_policies": SLAPolicies,
}
