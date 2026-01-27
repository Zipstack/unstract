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

```bash
cd unstract/connectors

# Install test dependencies
uv sync --group test

# Run all tests for a connector
uv run pytest tests/filesystems/test_sharepoint_fs.py -v

# Run unit tests only
uv run pytest tests/filesystems/test_sharepoint_fs.py::TestSharePointFSUnit -v

# Run integration tests (requires .env credentials)
uv run pytest tests/filesystems/test_sharepoint_fs.py::TestSharePointFSIntegration -v -s
```
