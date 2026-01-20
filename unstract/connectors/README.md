<div align="center">
<img src="docs/assets/unstract_u_logo.png" style="height: 120px">

# Unstract

## No-code LLM Platform to launch APIs and ETL Pipelines to structure unstructured documents

</div>

# Unstract Connectors

This is Unstract's python package which helps connect to a number of different filesystems and databases.

## Filesystems
Filesystems are supported with the help of [fsspec](https://filesystem-spec.readthedocs.io/en/latest/) libraries that provide a uniform interface to these connectors.

The following filesystems are supported
- Google Drive
- S3/Minio
- Unstract Cloud Storage
- Box
- Dropbox (issues exist around file discovery/listing)
- SharePoint / OneDrive
- HTTP(S)

## Databases
The following databases are supported
- Snowflake
- PostgreSQL
- MySQL
- MSSQL
- Redshift
- MariaDB
- BigQuery

## Installation

### Local Development

To get started with local development,
- Create and source a virtual environment if you haven't already following [these steps](/README.md#create-your-virtual-env).
- If you're using Mac, install the below library needed for PyMSSQL
```
brew install pkg-config freetds
```
- Install the required dependencies with
```shell
uv sync
```

### Environment variables
If the [GCSHelper](/src/unstract/connectors/gcs_helper.py) is used, the following environment variables need to be set
- GOOGLE_SERVICE_ACCOUNT : The service account JSON to perform authentication with Google Cloud Storage account.
- GOOGLE_PROJECT_ID : The project ID associated with the Google Cloud Storage account.

### Running tests

#### Connector-Specific Testing
For detailed setup and integration testing:
1. Copy `sample.env` to `.env` in the connectors directory
2. Configure connector credentials in `.env`

#### Running Unit Tests

Tests should be run from the **main `unstract` repository directory** to ensure all dependencies are available.

```bash
# From the main unstract directory
cd /path/to/unstract

source .venv/bin/activate

# Examples of SharePoint connector
uv run pytest unstract/connectors/tests/filesystems/test_sharepoint_fs.py::TestSharePointFSUnit -v
uv run pytest unstract/connectors/tests/filesystems/test_sharepoint_fs.py::TestSharePointFSUnit::test_connector_metadata -v

# Examples of MariaDB connector
uv run pytest unstract/connectors/tests/databases/test_mariadb.py -v
uv run pytest unstract/connectors/tests/databases/test_mariadb.py::TestMariaDB::test_ssl_config_from_environment -v
```
**Note:** Unit tests don't require credentials. Integration tests (if present) need a configured `.env` file with real credentials.
