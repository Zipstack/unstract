# Unstract DB Setup Script

[The db_setup.sh](/docker/scripts/db-setup/db_setup.sh) script helps setup the postgres database by making use of environment variables defined in the `.essentials.env` (user copy of the [sample.essentials.env](/docker/sample.essentials.env))

- POSTGRES_USER
- POSTGRES_DB
- POSTGRES_SCHEMA

This script helps setup the DB user and creates a new schema as well.
