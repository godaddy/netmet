Secure Netmet Server API
========================

Netmet Server supports basic auth for any potentially dangeours method:

GET /api/v2/config
POST /api/v2/config
POST /api/v1/events/<event_id>
DELETE /api/v1/events/<event_id>
POST /api/v1/events/<event_id>/_stop


To Enable Basic Auth
--------------------

Set enviorment variable

    NETMET_AUTH="<user1>:<password1>,<user2>:<password2>"

password should have at least 1 number and 1 uppercase 1 lowercase and
more then 6 characters.


This is temporary soultion that is going to be replaced by full RBAC.


Secure Netmet Server <-> Netmet Client Traffic
==============================================

Intro
-----

Type of Inteactions:
1) Netmet Server sets Netmet Config via POST /api/v2/config
2) Netmet Server disables Netmet Client via POST /api/v1/unregister
3) Netmet Client restores it's config via POST /api/clients/<host>/<port>
4) Netmet Client sends metrics to Netmet Server via POST /api/v1/metrics


In interactions are not secured anybody can perform any of this operations.
Which means that one can changed configuration of client, or send own metrics
back and they are going to process.

In trusted enviorment it may be OK.
However, Netmet provides simple way to secure this interaction and avoid
potential risks.

To do that Netmet uses HMAC mechanism.
Data that is send during these requests is singed with HMAC key, and other
side validates HMAC signature and drops requests with invalid signature.


How To Run NetMet Without HMAC
------------------------------

Set Env variable:

    NETMET_HMAC_SKIP=True


How To Enable HMAC
------------------

Provide to Netmet Server or Client:

    NETMET_HMACS="key1"

You can provide multiple keys, e.g. "key1,key2". First key is going to be
used to sign data, both for check signature.


How To Add HMAC To Existing Netmet Deployment
---------------------------------------------

1) Re run netmet server specifing:

   NETMET_HMAC_SKIP=True
   NETMET_HMACS="your_key"

2) Re run all netmet clients with

    NETMET_HMACS="your_key"

3) Re run all netmet servers with

    NETMET_HMACS="your_key"


How To Perform Rolling Upgrade of Netmet HMAC Keys
--------------------------------------------------

1) Re run NetMet Servers with

    NETMET_HMACS="<old_key>,<new_key>"


2) Re run NetMet Clients with

    NETMET_HMACS="<new_key>,<old_key>"

3) Re run Netmet Servers with

    NETMET_HMACS="<new_key>"

4) Re run Netmet Clients with

    NETMET_HMACS="<new_key>"

