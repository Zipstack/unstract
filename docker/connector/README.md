# Docker Run

Useful while running connectors 
- Database connectors: Includes db connectors like mysql, mariadb, mssql
- File system connectors: Includes fs connectors like sftp

**NOTE**: Copy `sample.env` into `.env` and update the necessary variables.

```bash
# Up all connector db
docker compose -f docker-compose-connector.yaml up -d

# Up a specific service alone
docker compose -f docker-compose-connector.yaml up -d mysql
```
