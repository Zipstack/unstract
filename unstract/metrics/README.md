# Unstract Metrics Aggregator

Helps collect metrics from Unstract and its adapters and pushes them to Elasticsearch.

Run the below services with the compose profile `unstract-metrics`.
- elasticsearch
- cerebro (UI for managing es instance)

```shell
VERSION=<version> docker compose -f docker-compose.yaml --profile unstract-metrics up -d 
```


## Using Cerebro: An Elasticsearch Web Admin tool

- Run Cerebro with

```shell
VERSION=<version> docker compose -f docker-compose.yaml --profile unstract-metrics up -d cerebro
```

- Connect to `http://localhost:9201/` with the node address of `http://es:9200/`
