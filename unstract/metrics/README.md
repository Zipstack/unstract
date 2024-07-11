# Unstract Metrics Aggregator

Helps collect metrics from Unstract and its adapters and pushes them to Elasticsearch.

Run `elasticsearch` with the compose profile `unstract-metrics`.

```shell
VERSION=<version> docker compose -f docker-compose.yaml --profile unstract-metrics up -d 
```
