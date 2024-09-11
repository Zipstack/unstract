# V2 Migrations and Commands

This folder contains scripts and management commands for performing data migrations from v1 to v2 for the Unstract Multitenancy system.

## Overview

The commands provided here help you manage the migration process, including creating and dropping schemas and applying the necessary migrations to transition from v1 to v2.

## Available Commands

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
- Ensure you have backups of your data before running migration commands.
- Verify your database configuration and environment variables are correctly set.
- Review the migration logs for any issues or errors during the migration process.

For more details on each command and its options, refer to the command help output using 
```bash
python manage.py help <command_name>
```
