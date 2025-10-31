[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/zipstack-unstract-badge.png)](https://mseep.ai/app/zipstack-unstract)

<div align="center">
<img src="docs/assets/unstract_u_logo.png" style="height: 120px">

# Unstract

## The Data Layer for your Agentic Workflows—Automate Document-based workflows with close to 100% accuracy!


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

Prompt Studio is a purpose-built environment that supercharges your schema definition efforts. Compare outputs from different LLMs side-by-side, keep tab on costs while you develop generic prompts that work across wide-ranging document variations. And when you're ready, launch extraction APIs with a single click.

![img Prompt Studio](docs/assets/prompt_studio.png)

## 🔌 Integrations that suit your environment

Once you've used Prompt Studio to define your schema, Unstract makes it easy to integrate into your existing workflows. Simply choose the integration type that best fits your environment:

| Integration Type | Description | Best For | Documentation |
|------------------|-------------|----------|---------------|
| 🖥️ **MCP Servers** | Run Unstract as an MCP Server to provide structured data extraction to Agents or LLMs in your ecosystem. | Developers building **Agentic/LLM apps/tools** that speak MCP. | [Unstract MCP Server Docs](https://docs.unstract.com/unstract/unstract_platform/mcp/unstract_platform_mcp_server/) |
| 🌐 **API Deployments** | Turn any document into JSON with an API call. Deploy any Prompt Studio project as a REST API endpoint with a single click. | Teams needing **programmatic access** in apps, services, or custom tooling. | [API Deployment Docs](https://docs.unstract.com/unstract/unstract_platform/api_deployment/unstract_api_deployment_intro/) |
| ⚙️ **ETL Pipelines** | Embed Unstract directly into your ETL jobs to transform unstructured data before loading it into your warehouse / database. | **Engineering and Data engineering teams** that need to batch process documents into clean JSON. | [ETL Pipelines Docs](https://docs.unstract.com/unstract/unstract_platform/etl_pipeline/unstract_etl_pipeline_intro/) |
| 🧩 **n8n Nodes** | Use Unstract as ready-made nodes in n8n workflows for drag-and-drop automation. | **Low-code users** and **ops teams** automating workflows. | [Unstract n8n Nodes Docs](https://docs.unstract.com/unstract/unstract_platform/api_deployment/unstract_api_deployment_n8n_custom_node/) |

## ☁️ Getting Started (Cloud / Enterprise)

The easy-peasy way to try Unstract is to [sign up for a **14-day free trial**](https://unstract.com/start-for-free/). Give Unstract a spin now!  

Unstract Cloud also comes with some really awesome features that give serious accuracy boosts to agentic/LLM-powered document-centric workflows in the enterprise.

| Feature | Description | Documentation |
|---------|-------------|---------------|
| 🧪 **LLMChallenge** | Uses two Large Language Models to ensure trustworthy output. You either get the right response or no response at all. | [Docs](https://docs.unstract.com/unstract/unstract_platform/features/llm_challenge/llm_challenge_intro/) |
| ⚡ **SinglePass Extraction** | Reduces LLM token usage by up to **8x**, dramatically cutting costs. | [Docs](https://docs.unstract.com/unstract/editions/cloud_edition/#singlepass-extraction) |
| 📉 **SummarizedExtraction** | Reduces LLM token usage by up to **6x**, saving costs while keeping accuracy. | [Docs](https://docs.unstract.com/unstract/unstract_platform/features/summarized_extraction/summarized_extraction_intro/) |
| 👀 **Human-In-The-Loop** | Side-by-side comparison of extracted value and source document, with highlighting for human review and tweaking. | [Docs](https://docs.unstract.com/unstract/unstract_platform/human_quality_review/human_quality_review_intro/) |
| 🔐 **SSO Support** | Enterprise-ready authentication options for seamless onboarding and off-boarding. | [Docs](https://docs.unstract.com/unstract/editions/cloud_edition/#enterprise-features) |

## ⏩ Quick Start Guide

Unstract comes well documented. You can get introduced to the [basics of Unstract](https://docs.unstract.com/unstract/), and [learn how to connect](https://docs.unstract.com/unstract/unstract_platform/setup_accounts/whats_needed) various systems like LLMs, Vector Databases, Embedding Models and Text Extractors to it. The easiest way to wet your feet is to go through our [Quick Start Guide](https://docs.unstract.com/unstract/unstract_platform/quick_start) where you actually get to do some prompt engineering in Prompt Studio and launch an API to structure varied credit card statements!

## 🚀 Getting started (self-hosted)

### System Requirements

- 8GB RAM (minimum)

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
