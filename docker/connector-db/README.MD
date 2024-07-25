# Docker Run

Useful while running database connectors like mysql, mariadb, mssql

**NOTE**: First copy `sample.*.env` files to `*.env` and update as required.

```bash
# Up all connector db
docker compose -f docker-compose-db-connector.yaml up -d

# Up a specific service alone
docker compose -f docker-compose-db-connector.yaml up -d mysql
```
