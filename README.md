<div align="center">
<img src="docs/assets/unstract_u_logo.png" style="height: 120px">

# Unstract

## No-code LLM Platform to launch APIs and ETL Pipelines to structure unstructured documents

##

![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FZipstack%2Funstract%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
![GitHub License](https://img.shields.io/github/license/Zipstack/unstract)
![Docker Pulls](https://img.shields.io/docker/pulls/unstract/backend)
[![CLA assistant](https://cla-assistant.io/readme/badge/Zipstack/unstract)](https://cla-assistant.io/Zipstack/unstract)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/Zipstack/unstract/main.svg)](https://results.pre-commit.ci/latest/github/Zipstack/unstract/main)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=Zipstack_unstract&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=Zipstack_unstract)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=Zipstack_unstract&metric=bugs)](https://sonarcloud.io/summary/new_code?id=Zipstack_unstract)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=Zipstack_unstract&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=Zipstack_unstract)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=Zipstack_unstract&metric=coverage)](https://sonarcloud.io/summary/new_code?id=Zipstack_unstract)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=Zipstack_unstract&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=Zipstack_unstract)

</div>

## 🤖 Prompt Studio

Prompt Studio's primary reason for existence is so you can develop the necessary prompts for document data extraction super efficiently. It is a purpose-built environment that makes this not just easy for you—but, lot of fun! The document sample, its variants, the prompts you're developing, outputs from different LLMs, the schema you're developing, costing details of the extraction and various tools that let you measure the effectiveness of your prompts are just a click away and easily accessible. Prompt Studio is designed for effective and high speed development and iteration of prompts for document data extraction. Welcome to IDP 2.0!


![img Prompt Studio](docs/assets/prompt_studio.png)

## 🧘‍♀️ Three step nirvana with Workflow Studio

Automate critical business processes that involve complex documents with a human in the loop. Go beyond RPA with the power of Large Language Models.

🌟 **Step 1**: Add documents to no-code Prompt Studio and do prompt engineering to extract required fields <br>
🌟 **Step 2**: Configure Prompt Studio project as API deployment or configure input source and output destination for ETL Pipeline<br>
🌟 **Step 3**: Deploy Workflows as unstructured data APIs or unstructured data ETL Pipelines!

![img Using Unstract](docs/assets/Using_Unstract.png)

## 🚀 Getting started

### System Requirements

- 8GB RAM (recommended)

### Prerequisites

- Linux or MacOS (Intel or M-series)
- Docker
- Docker Compose (if you need to install it separately)
- Git

Next, either download a release or clone this repo and do the following:

✅ `./run-platform.sh`<br>
✅ Now visit [http://frontend.unstract.localhost](http://frontend.unstract.localhost) in your browser <br>
✅ Use username and password `unstract` to login


That's all there is to it!

Follow [these steps](backend/README.md#authentication) to change the default username and password.
See [user guide](https://docs.unstract.com/unstract/unstract_platform/user_guides/run_platform) for more details on managing the platform.

Another really quick way to experience Unstract is by signing up for our [hosted version](https://us-central.unstract.com/). It comes with a 14 day free trial!

## 📄 Supported File Types

Unstract supports a wide range of file formats for document processing:

| Category | Format | Description |
|----------|---------|-------------|
| **Word Processing** | DOCX | Microsoft Word Open XML |
| | DOC | Microsoft Word |
| | ODT | OpenDocument Text |
| **Presentation** | PPTX | Microsoft PowerPoint Open XML |
| | PPT | Microsoft PowerPoint |
| | ODP | OpenDocument Presentation |
| **Spreadsheet** | XLSX | Microsoft Excel Open XML |
| | XLS | Microsoft Excel |
| | ODS | OpenDocument Spreadsheet |
| **Document & Text** | PDF | Portable Document Format |
| | TXT | Plain Text |
| | CSV | Comma-Separated Values |
| | JSON | JavaScript Object Notation |
| **Image** | BMP | Bitmap Image |
| | GIF | Graphics Interchange Format |
| | JPEG | Joint Photographic Experts Group |
| | JPG | Joint Photographic Experts Group |
| | PNG | Portable Network Graphics |
| | TIF | Tagged Image File Format |
| | TIFF | Tagged Image File Format |
| | WEBP | Web Picture Format |

## ⏩ Quick Start Guide

Unstract comes well documented. You can get introduced to the [basics of Unstract](https://docs.unstract.com/unstract/), and [learn how to connect](https://docs.unstract.com/unstract/unstract_platform/setup_accounts/whats_needed) various systems like LLMs, Vector Databases, Embedding Models and Text Extractors to it. The easiest way to wet your feet is to go through our [Quick Start Guide](https://docs.unstract.com/unstract/unstract_platform/quick_start) where you actually get to do some prompt engineering in Prompt Studio and launch an API to structure varied credit card statements!

## 🤝 Ecosystem support

### LLM Providers

|| Provider                                                       | Status                      |
|----------------------------------------------------------------|-----------------------------|---|
| <img src="docs/assets/3rd_party/openai.png" width="32"/>       | OpenAI                      | ✅ Working |
| <img src="docs/assets/3rd_party/vertex_ai.png" width="32"/>    | Google VertexAI, Gemini Pro | ✅ Working |
| <img src="docs/assets/3rd_party/azure_openai.png" width="32"/> | Azure OpenAI                | ✅ Working |
| <img src="docs/assets/3rd_party/anthropic.png" width="32"/>    | Anthropic                   | ✅ Working |
| <img src="docs/assets/3rd_party/ollama.png" width="32"/>       | Ollama                      | ✅ Working |
| <img src="docs/assets/3rd_party/bedrock.png" width="32"/>      | Bedrock                     | ✅ Working |
| <img src="docs/assets/3rd_party/palm.png" width="32"/>         | Google PaLM                 | ✅ Working |
| <img src="docs/assets/3rd_party/anyscale.png" width="32"/>     | Anyscale                    | ✅ Working |
| <img src="docs/assets/3rd_party/mistral_ai.png" width="32"/>   | Mistral AI                  | ✅ Working |


### Vector Databases

|| Provider | Status |
|---|---|---|
|<img src="docs/assets/3rd_party/qdrant.png" width="32"/>| Qdrant | ✅ Working |
|<img src="docs/assets/3rd_party/weaviate.png" width="32"/>| Weaviate | ✅ Working |
|<img src="docs/assets/3rd_party/pinecone.png" width="32"/>| Pinecone | ✅ Working |
|<img src="docs/assets/3rd_party/postgres.png" width="32"/>| PostgreSQL | ✅ Working |
|<img src="docs/assets/3rd_party/milvus.png" width="32"/>| Milvus | ✅ Working |



### Embeddings

|| Provider | Status |
|---|---|---|
|<img src="docs/assets/3rd_party/openai.png" width="32"/>| OpenAI | ✅ Working |
|<img src="docs/assets/3rd_party/azure_openai.png" width="32"/>| Azure OpenAI | ✅ Working  |
|<img src="docs/assets/3rd_party/palm.png" width="32"/>| Google PaLM | ✅ Working  |
|<img src="docs/assets/3rd_party/ollama.png" width="32"/>| Ollama | ✅ Working |
|<img src="docs/assets/3rd_party/vertex_ai.png" width="32"/>    | VertexAI | ✅ Working |
| <img src="docs/assets/3rd_party/bedrock.png" width="32"/>      | Bedrock                     | ✅ Working |

### Text Extractors

|| Provider                   | Status |
|---|----------------------------|---|
|<img src="docs/assets/unstract_u_logo.png" width="32"/>| Unstract LLMWhisperer V2   | ✅ Working |
|<img src="docs/assets/3rd_party/unstructured_io.png" width="32"/>| Unstructured.io Community  | ✅ Working |
|<img src="docs/assets/3rd_party/unstructured_io.png" width="32"/>| Unstructured.io Enterprise | ✅ Working |
|<img src="docs/assets/3rd_party/llamaindex.png" width="32"/>| LlamaIndex Parse           | ✅ Working |

### ETL Sources

|| Provider | Status |
|---|---|---|
|<img src="docs/assets/3rd_party/s3.png" width="32"/>| AWS S3 | ✅ Working |
|<img src="docs/assets/3rd_party/minio.png" width="32"/>| MinIO | ✅ Working |
|<img src="docs/assets/3rd_party/gcp.png" width="32"/>| Google Cloud Storage | ✅ Working |
|<img src="docs/assets/3rd_party/azure_openai.png" width="32"/>| Azure Cloud Storage | ✅ Working |
|<img src="docs/assets/3rd_party/google_drive.png" width="32"/>| Google Drive | ✅ Working |
|<img src="docs/assets/3rd_party/dropbox.png" width="32"/>| Dropbox | ✅ Working |
|<img src="docs/assets/3rd_party/sftp.png" width="32"/>| SFTP | ✅ Working |

### ETL Destinations

|                                                                   | Provider             | Status |
|-------------------------------------------------------------------|----------------------|---|
| <img src="docs/assets/3rd_party/snowflake.png" width="32"/>       | Snowflake            | ✅ Working |
| <img src="docs/assets/3rd_party/amazon_redshift.png" width="32"/> | Amazon Redshift      | ✅ Working |
| <img src="docs/assets/3rd_party/google_bigquery.png" width="32"/> | Google BigQuery      | ✅ Working |
| <img src="docs/assets/3rd_party/postgres.png" width="32"/>        | PostgreSQL           | ✅ Working |
| <img src="docs/assets/3rd_party/mysql.png" width="32"/>           | MySQL                | ✅ Working |
| <img src="docs/assets/3rd_party/mariadb.png" width="32"/>         | MariaDB              | ✅ Working |
| <img src="docs/assets/3rd_party/ms_sql.png" width="32"/>          | Microsoft SQL Server | ✅ Working |
| <img src="docs/assets/3rd_party/oracle.png" width="32"/>          | Oracle               | ✅ Working |

## 🙌 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for further details to get started easily.

## 👋 Join the LLM-powered automation community

- On Slack, [join great conversations](https://join-slack.unstract.com) around LLMs, their ecosystem and leveraging them to automate the previously unautomatable!
- [Follow us on X/Twitter](https://twitter.com/GetUnstract)
- [Follow us on LinkedIn](https://www.linkedin.com/showcase/unstract/)

## 🚨 Backup encryption key

Do copy the value of `ENCRYPTION_KEY` config in either `backend/.env` or `platform-service/.env` file to a secure location.

Adapter credentials are encrypted by the platform using this key. Its loss or change will make all existing adapters inaccessible!

## 📊 A note on analytics

In full disclosure, Unstract integrates Posthog to track usage analytics. As you can inspect the relevant code here, we collect the minimum possible metrics. Posthog can be disabled if desired by setting `REACT_APP_ENABLE_POSTHOG` to `false` in the frontend's .env file.
