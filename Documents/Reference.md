# Description

Zendesk API offers data related with customer issues handled in the platform as tickets, users, organizations, groups, tags etc.

For a complete overview, refer to [Zendesk API](https://developer.zendesk.com/api-reference/)

***



# Supported Features

| **Feature Name**                                                                                                                                                                            | **Supported** | **Comment** |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------- |
| [Full Import](https://docs.y42.com/docs/features#full-import)                                                                                                                               | Yes           |             |
| [Incremental Import](https://docs.y42.com/docs/features#partial-import)                                                                                                                         | Yes           | Only for   `organizations`, `users`, `tickets`, `ticket_audits`, `ticket_metrics`, `ticket_comments`, `satisfaction_ratings`, `groups`, `macros`, `ticket_fields`, `ticket_forms`, `group_memberships`|
| [Re-Sync](https://docs.y42.com/docs/features#re-sync)                                                                                                                                       | Yes           |             |
| [Start Date Selection](https://docs.y42.com/docs/features#start-date-selection)                                                                                                             | Yes           |             |
| [Import Empty Tables](https://docs.y42.com/docs/features#import-empty-table)                                                                                                                | No            |             |
| [Custom Data](https://docs.y42.com/docs/features#custom-data)                                                                                                                               | No            |             |
| [Retroactive Updating](https://docs.y42.com/docs/features#retroactive-updating)                                                                                                             | No            |             |
| [Dynamic Column Selection](https://docs.y42.com/docs/features#dynamic-column-selection)                                                                                                     | Yes           |             |

***



# Sync Overview

**Performance Consideration**

Under normal use you will not have problems following the \[requests limitation (<https://developer.zendesk.com/api-reference/ticketing/account-configuration/usage_limits/>)

***



# Connector <img src="https://svgshare.com/i/jCQ.svg" width=12% height=20%  />  <img src="https://svgshare.com/i/jDa.svg" width=12% height=20% /> <img src="https://svgshare.com/i/jAT.svg" width=12% height=20% />

This connector was developed following the standards of Singer SDK.  
For more details, see the [Singer](https://github.com/singer-io/getting-started)

### Authentication

- OAuth is the default authentication method for `tap-zendesk`. To use OAuth, you will need to fetch an `access_token` from a configured Zendesk integration. See [here](https://support.zendesk.com/hc/en-us/articles/203663836) for more details on how to integrate your application with Zendesk.


---

# Schema

This source is based on the [zendesk developers](https://developer.zendesk.com/documentation/ticketing/getting-started/zendesk-api-quick-start/), and is currently in the version v2.

## Supported Streams

| **Name**<br>*With hyperlink to the original API reference* | **Description**<br>*What data can be found inside* | **Stream Type** <br>*Where this data is from*|
| --- | --- | --- | 
| [Group Memberships](https://developer.zendesk.com/api-reference/ticketing/groups/group_memberships/) |  List what agents are in which groups, and reassign group members  |  | 
| [Groups] (https://developer.zendesk.com/api-reference/ticketing/groups/groups/)| Define organisation of tickets and agents |  |
| [Macros](https://developer.zendesk.com/api-reference/ticketing/business-rules/macros/) | A macro id made of one or more actions that can modify the values of a ticket's fields. |  |
| [Organizations](https://developer.zendesk.com/api-reference/ticketing/organizations/organizations/) | Represent group of customers. |  |
| [Satisfaction Ratings](https://developer.zendesk.com/api-reference/ticketing/ticket-management/satisfaction_ratings/) | We can retrieve all ratings if we have enabled in our account |  |
| [SLA Policies](https://developer.zendesk.com/api-reference/ticketing/business-rules/sla_policies/) | A Service Level Agreement is a document for support provider and customers with rules about their  agreement|  |
| [Tags](https://developer.zendesk.com/api-reference/ticketing/ticket-management/tags/) | Tagging of users and organizations. Must enable it in Zendesk Support|  |
| [Ticket Audits](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_audits/) | Stores all the changes history for a ticket. |  |
| [Ticket Comments](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/) | Conversation between requesters, collaborators, and agents. |  |
| [Ticket Fields](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_fields/) | Retrieve all custom and default fields for a ticket. |  |
| [Ticket Forms](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_forms/) | Ticket Forms are pre defined subset of ticket fields to display to both agents and end users. |  |
| [Ticket Metrics](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_metrics/) | Retrieve metrics for one or more tickets. |  |
| [Tickets](https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/) | Base of communication between customers and agents. |  |
| [Users](https://developer.zendesk.com/api-reference/ticketing/users/users/) | All users include customers, agent and administrators. |  |

 
