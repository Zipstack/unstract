# V2 Migration Guide

This folder contains scripts and management commands for performing data migrations from v1 to v2 for the Unstract Multitenancy system.
From version `v0.93.0` onwards, there have been signifcant changes in how data is stored. This warrants a data migration and the below steps can come in handy.

> [!WARNING]
> If you're updating from a very old version of Unstract and you face issues, its recommended to update to `v0.92.1` with 
`./run-platform.sh -u -v v0.92.1` first and then perform this data migration.

## Performing the migration

> [!TIP]
> If the existing data is important to you, consider [backing up and restoring to a new database](/backend/migrating/v2/README.md#preparing-for-the-migration-safest-approach) beforehand.

Run the `migrate-to-v2.sh` script to perform schema and data migrations in one shot.

```shell
./migrate-to-v2.sh
```

If you prefer explicitly executing the migration commands, refer [these steps below](/backend/migrating/v2/README.md#manually-performing-V2-migration)

## Preparing for the migration (safest approach)

Follow below steps to backup existing data in case of any issues during the migration

### Backup existing data

- Make sure `pg_dump` is installed. This would usually be bundled with postgres and can be installed with

```shell
sudo apt-get install postgresql-client
```

- Take a backup of the existing data with the below command (provide the appropriate options)

```shell
pg_dump -h localhost -p 5432 -U unstract_dev -d unstract_db -f unstract-backup-$(date +"%Y-%m-%d_%H-%M-%S").sql
```

### Create a new database

- Create a new database, for example `unstract_db_v2`

### Restore backup to the new database

- Exec into the DB if required (from [/docker](/docker/))

```shell
docker exec -it unstract-db /bin/bash
```

- Execute the below command to restore the backup in the new DB

```shell
psql -h localhost -p 5432 -U unstract_dev -d unstract_db_v2 -f unstract-backup-<DateTime>.sql
```

## Manually performing V2 migration

### Configuring the env

- Make sure to update all the necessary `.env` files
- For example, in case of `v2` ensure `backend`, `prompt-service`, and `platform-service` `.env` contain `DB_SCHEMA=unstract_v2`

### Create a new schema

- Create a new schema within the above DB, for example `unstract_v2`
- This can be done directly in the DB or
- Run the command supported from [/backend/manage.py](/backend/manage.py), for example in case of `v2`

```shell
python manage.py create_v2_schema
```

### Run schema migrations

- Schema migrations are run by django, this gets invoked when running the backend service
- Or run it explicitly with

```shell
python manage.py migrate
```

- This ensures that the required tables are created or altered

### Run data migrations

- This helps move the existing data from your current schema to the new schema
- It can either be run locally or within the backend container

```shell
docker exec -it unstract-backend /bin/bash
```

- Make sure to activate the virtual environment

```shell
source .venv/bin/activate
```

- Perform the data migration

```shell
python manage.py migrate_to_v2
```

- Test to see if the applied migrations work as expected.

## Django Commands Reference

The commands provided here help you manage the migration process, including creating and dropping schemas and applying the necessary migrations to transition from v1 to v2.

**Pre-requisites:**
Ensure that `migrating.v2` is added to the `SHARED_APPS` in your Django settings.

### 1. List Commands

To view all available management commands, use:

```bash
python manage.py help
```

### 2. Create V2 Schema

To set up the v2 schema in your database, execute:

```bash
python manage.py create_v2_schema
```

This command initializes the schema required for v2 migrations.

### 3. Drop V2 Schema

To remove the v2 schema from your database, run:

```bash
python manage.py drop_v2_schema
```

Note: Use this command with caution as it will permanently delete the v2 schema and its associated data.

### 4. Migrate to V2 Schema

To apply migrations and transition data from v1 to v2, use:

```bash
python manage.py migrate_to_v2
```

This command performs the migration, updating your database to the v2 schema and transforming the data accordingly.

## Notes

- Ensure you have backed up your data before attempting any migration.
- Verify your database configuration and environment variables are correctly set.
- Review the migration logs for any issues or errors during the migration process.

For more details on each command and its options, refer to the command help output using

```bash
python manage.py help <command_name>
```
