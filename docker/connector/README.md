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

## MSSQL Limited User Setup

For testing database permission error scenarios, you can create a restricted MSSQL user with limited permissions.

### Environment Variables

The following environment variables are used for the limited user setup:

```bash
MSSQL_LIMITED_USER=unstract_limited_user
MSSQL_LIMITED_PASSWORD=limitedPass@123
MSSQL_LIMITED_DATABASE=unstract_test_db
```

### Setup Instructions

1. **Start MSSQL container:**
```bash
docker compose -f docker-compose-connector.yaml up -d mssql
```

2. **Connect as SA user and create limited user:**
```bash
docker exec -it unstract-mssql /opt/mssql-tools18/bin/sqlcmd -S localhost -U SA -P 'unstractPassword@123' -C
```

3. **Execute SQL commands to create restricted user:**
```sql
-- Create test database
CREATE DATABASE unstract_test_db;
GO

-- Create login and user
CREATE LOGIN unstract_limited_user WITH PASSWORD = 'limitedPass@123';
GO

USE unstract_test_db;
GO

-- Create user in database
CREATE USER unstract_limited_user FOR LOGIN unstract_limited_user;
GO

-- Create test schema
CREATE SCHEMA test_schema_1;
GO

-- Grant minimal permissions (no ALTER or UPDATE)
GRANT CONNECT TO unstract_limited_user;
GO
GRANT SELECT, INSERT, DELETE ON SCHEMA::dbo TO unstract_limited_user;
GO
GRANT SELECT, INSERT, DELETE ON SCHEMA::test_schema_1 TO unstract_limited_user;
GO

-- Explicitly deny ALTER and UPDATE permissions
DENY ALTER ON SCHEMA::dbo TO unstract_limited_user;
GO
DENY ALTER ON SCHEMA::test_schema_1 TO unstract_limited_user;
GO
DENY UPDATE ON SCHEMA::dbo TO unstract_limited_user;
GO
DENY UPDATE ON SCHEMA::test_schema_1 TO unstract_limited_user;
GO

quit
```

4. **Test the limited user connection:**
```bash
docker exec -it unstract-mssql /opt/mssql-tools18/bin/sqlcmd -S localhost -U unstract_limited_user -P 'limitedPass@123' -d unstract_test_db -C
```

### What This Setup Provides

**Allowed Operations:**
- ✅ SELECT data from tables
- ✅ INSERT data into existing tables
- ✅ DELETE data from tables

**Denied Operations (for error testing):**
- ❌ CREATE TABLE (triggers permission denied errors)
- ❌ ALTER TABLE (prevents table migration)
- ❌ UPDATE data (additional restriction)

### Testing Error Scenarios

This setup is perfect for testing database permission error handling in your application:

1. **CREATE TABLE Permission Denied**: When the application tries to create new tables
2. **ALTER TABLE Permission Denied**: When the application tries to perform table migrations
3. **UPDATE Permission Denied**: When the application tries to update existing records

The restricted user will trigger real database permission errors that your application needs to handle gracefully.
