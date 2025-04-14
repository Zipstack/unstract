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

TODO: Use a test framework and document way to run tests
