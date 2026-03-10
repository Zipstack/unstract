# Unstract DB Setup Script

[The db_setup.sh](/docker/scripts/db-setup/db_setup.sh) script helps setup the postgres database by making use of environment variables derived from the `.env` (user copy of [sample.common.env](/docker/sample.common.env)). The Postgres container receives these via docker-compose environment mappings:

- POSTGRES_USER (mapped from DB_USER)
- POSTGRES_DB (mapped from DB_NAME)
- POSTGRES_SCHEMA (mapped from DB_SCHEMA)

This script helps setup the DB user and creates a new schema as well.
