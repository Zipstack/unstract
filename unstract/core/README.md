# Packaging

Create a repository
Create the repository for your packages.

1. Run the following command to create a new Python package repository in the current project named pandora-core in the location us-central1.

```
gcloud artifacts repositories create pandora\
    --repository-format=python \
    --location=us-central1 \
    --description="Python package repository for pandora-core"
```

2. Run the following command to verify that your repository was created:

```
gcloud artifacts repositories list
```

3. To simplify gcloud commands, set the default repository to pandora  and the default location to us-central1. After the values are set, you do not need to specify them in gcloud commands that require a repository or a location.

To set the repository, run the command:

gcloud config set artifacts/repository  pandora

To set the location, run the command:

gcloud config set artifacts/location us-central1

## Build package

In the root directory of your Python module, create a setup.py script. This script provides metadata about your package and allows you to specify its dependencies, version, etc.

Next, build your Python package. In the same directory as your setup.py, run:

```
python setup.py sdist bdist_wheel 
```

### Configure authentication

The Artifact Registry keyring backend finds your credentials using Application Default Credentials (ADC), a strategy that looks for credentials in your environment.

In this quickstart, you'll:

Generate user credentials for ADC. In a production environment, you should use a service account and provide credentials with the GOOGLE_APPLICATION_CREDENTIALS environment variable.
Include the Artifact Registry repository URL in pip and twine commands so that you do not need to configure pip and Twine with the repository URL.
To generate credentials for ADC, run the following command:

```
gcloud auth application-default login
```

Publish Your Package to Artifact Registry:

Push your package to the configured Google Cloud Artifact Registry repository using twine. First, install twine if you haven't already:

```
pip install twine

```

Then, upload your package:

```
twine upload --repository-url https://REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME dist/*
twine upload --repository-url https://us-central1-python.pkg.dev/pandora-engineering-trials/pandora/ dist/*
```

[global]
index-url = https://_json_key_base64:<KEY@LOCATION-python.pkg.dev>/PROJECT/REPOSITORY/simple/

gcloud artifacts print-settings python --project=pandora-engineering-trials \
    --repository=pandora \
    --location=us-central1

pip install --extra-index-url https://_json_key_base64:<KEY@LOCATION-python.pkg.dev>/PROJECT/REPOSITORY/simple/ pandora_core

pip install --extra-index-url <https://us-central1-python.pkg.dev/pandora-engineering-trials/pandora/simple> pandora_core

gcloud artifacts print-settings python --project=pandora-engineering-trials \
    --repository=pandora \
    --location=us-central1 \
    --json-key=./gcloud.json

## Pull image

Install Gclud

docker build -t backend:prod -f Dockerfile.prod .  

list packages : python -m pip list

python -m twine upload --repository-url <https://us-central1-python.pkg.dev/pandora-engineering-trials/pandora/> dist/*

pip install --index-url <https://us-central1-python.pkg.dev/pandora-engineering-trials/pandora/simple> pandora_core
