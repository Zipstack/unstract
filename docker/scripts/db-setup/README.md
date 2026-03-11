# Unstract DB Setup Script

[The db_setup.sh](/docker/scripts/db-setup/db_setup.sh) script helps set up the postgres database by making use of environment variables derived from the `.env` (user copy of [sample.env](/docker/sample.env)). The Postgres container receives these via docker-compose environment mappings:

- POSTGRES_USER (mapped from DB_USER)
- POSTGRES_PASSWORD (mapped from DB_PASSWORD)
- POSTGRES_DB (mapped from DB_NAME)
- POSTGRES_SCHEMA (mapped from DB_SCHEMA)

This script helps set up the DB user and creates a new schema as well.
