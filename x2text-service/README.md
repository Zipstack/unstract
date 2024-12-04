# x2text-service

Flask service to act as bridge to https://github.com/Unstructured-IO/unstructured-api

The Flask service consists 3 APi's

- Test Connection - Validates the configured url and api key of unstructured io  API

```
curl --location 'http://{host}:{port}/api/v1/x2text/test-connection' \
--header 'accept: application/json' \
--header 'Authorization: Bearer <platform-key>' \
--form 'unstructured-url="https://api.unstructured.io/general/v0/general"' \
--form 'file=@"/home/johny/Documents/test_resume.pdf"' \
--form 'unstructured-api-key="<api-key>"'  

```

api-key will empty in case of community edition

```
Response samples:
status code : 200
{
    "message": "Test connection sucessful"
}
status code : 401
{
    "detail": "API key is malformed, please type the API key correctly in the header."
}
```


- Process Document - Takes in the the unstructed document and convert the same to text and download it as text file

```
curl --location 'http://{host}:{port}/api/v1/x2text/process' \
--header 'accept: application/json' \
--header 'Authorization: <platform-key>' \
--form 'unstructured-api-key="<api-key>"' \
--form 'unstructured-url="https://api.unstructured.io/general/v0/general"' \
--form 'file=@"/home/johny/Documents/test_resume1.pdf"


```

- Health - API to check if the falsk service is up and running
```
curl --location 'http://{host}:{port}/api/v1/x2text/health'

Response samples:
status code : 200
OK
```

## Migration for x2text_audit Table to New Schema
*(Applicable for users upgrading from versions before [v0.93.0](https://github.com/Zipstack/unstract/releases/tag/v0.93.0) to [v0.93.0](https://github.com/Zipstack/unstract/releases/tag/v0.93.0) or higher. This migration is not required for fresh installations or users already on v0.93.0 or a later version.)*

### Migration Description
This migration transfers data from the `public.x2text_audit_old` table to the `<db_schema>.x2text_audit` table. It ensures the new table and schema exist before inserting the data. The ON CONFLICT DO NOTHING clause prevents duplicate records during the migration.

- **Step 1: Update .env Configuration**: Ensure the `.env` file is updated with the correct value for `DB_SCHEMA`, as specified in `sample.env`. The value should match the `.env` configuration used in the `backend service`.
- **Step 2: Run the x2-Text Service**: Start the `x2-text service`. This step will automatically create the `x2text_audit` table in the schema defined by `DB_SCHEMA`.
- **Step 3: Execute the SQL Migration Query** *(Or Step 4)*: Run the following query in your database to migrate data from the old table to the new schema:

```sql
INSERT INTO <DB_SCHEMA>.x2text_audit (id, created_at, org_id, file_name, file_type, file_size_in_kb, status)
SELECT id, created_at, org_id, file_name, file_type, file_size_in_kb, status
FROM public.x2text_audit_old
ON CONFLICT DO NOTHING
```
Replace `<DB_SCHEMA>` with the actual schema name specified in the .env file.

- **Step 4: Optional Automation (Using `psql`)**
Alternatively, save the migration SQL in a file (e.g., `migration.sql`) and execute it using `psql`:
```bash
psql -U <username> -d <database_name> -f path/to/migration.sql
```
