# Elastic Search Requirements

Netmet is using Elasticsearch for storing all data including configuration.
Only 2 types of indexes are stored for now.

## `netmet_catalog`

It has two types:
* config - stores all configs of netmet server
* clients - stores information about all clients

### Index rollover

No need. Amount of recrods is small and Elastic can store all data in one index.

### Index Size

* Count of docs:  `O(netmet_clients)`
* Size of doc: `~100b`

## `netmet_data-<date>-<count>`

Stores raw data collected by netmet clients, such like pings, http pings and so on.

### Index rollover

* Performed automatically by netmet server. (Checks every 10 minutes)
* Conditions for rollover one of two: index older then one day, index has more than 10kk elements.

### Index Size

* Count of docs: `(types_of_traffic * netmet_clients² / period) per second`
* Max size of index: `10kk docs`
* Size of doc: `500 bytes`

### Load calculation

Input
* 34 clients
* 2 types of traffic (ICMP, HTTP)
* period = 5 seconds
* push_data_period = Every 10 seconds netmet client sends bulk of data to netmet server

Count of documents / day
* 2 * 34 * 34 * (60 / 5) * 60 * 24 = `~40kk documents per day`
* It's about ~20 GB of data.

Count of requests to netmet server
* clients / push_data_period = 34 / 10 = `~3.5 / second`

Count/Size of requests to elastic
* clients / push_data_to_server_period = 34 / 10 = `~3.5 / second`
* clients * types_of_traffic * push_data_period / period = 34 * 2 * 10 / 5 = `136 docs` in every bulk
