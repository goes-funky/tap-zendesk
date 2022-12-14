# Resources

The resources you need to be able to connect to this connector are:

- OAuth is the default authentication method for Zendesk Integration. To use OAuth, you will need to fetch an `access_token` from a configured Zendesk integration. See [here](https://support.zendesk.com/hc/en-us/articles/203663836) for more details on how to integrate your application with Zendesk.  
  -For a simplified, but less granular setup, you can use the API Token authentication which can be generated from the Zendesk Admin page. See [here](https://support.zendesk.com/hc/en-us/articles/226022787-Generating-a-new-API-token-) for more details about generating an API Token. You'll then be able to use the admins`email` and the generated `api_token` to authenticate.

***



# Connector Setup

## How to Get an account for Zendesk

1. Follow this [process](https://www.zendesk.com/register/#step-1) step by step.

## How to Create a new Connector

1. On Integrate, click on "Add..." to search for Zendesk and select it.
2. Name your integration.
3. To authorize fill the `Sub-Domain` and `Sync Historical Data from` next click Authorize, after will ask to authenticate with your account.
4. After authentication, you are good to go and start importing your tables.
