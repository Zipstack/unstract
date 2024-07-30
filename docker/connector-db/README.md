# Docker Run

Useful while running database connectors like mysql, mariadb, mssql

**NOTE**: Copy `sample.env` into `.env` and update the necessary variables.

```bash
# Up all connector db
docker compose -f docker-compose-db-connector.yaml up -d

# Up a specific service alone
docker compose -f docker-compose-db-connector.yaml up -d mysql
```
