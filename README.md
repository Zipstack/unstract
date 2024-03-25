<div align="center">
<img src="docs/assets/unstract_u_logo.png" style="height: 120px">

# Unstract

## No-code LLM Platform to launch APIs and ETL Pipelines to structure unstructured documents

</div>

## 🤖 Go beyond co-pilots

While co-pilots enable machine-to-human automation, with Unstract, you can go beyond co-pilots by enabling machine-to-machine automation. You can launch APIs that take in complex documents and return structured JSON all with a simple no-code approach. You can also launch unstructured data ETL Pipelines that can read complex documents from a variety of cloud file / object storage systems and write structured data into popular data warehouses and databases.

![img Prompt Studio](docs/assets/prompt_studio.png)

## 🧘‍♀️ Three step nirvana

Automate critical business processes that involve complex documents with a human in the loop. Go beyond RPA with the power of Large Language Models.

🌟 **Step 1**: Add documents to no-code Prompt Studio and do prompt engineering to extract required fields <br>
🌟 **Step 2**: Configure Prompt Studio project as API deployment or configure input source and output destination for ETL Pipeline<br>
🌟 **Step 3**: Deploy Workflows as unstructured data APIs or unstructured data ETL Pipelines!

![img Using Unstract](docs/assets/Using_Unstract.png)

## 🚀 Getting started

The easiest way to get started is with Docker. Either download a release or clone this repo and do the following:

✅ `./run-platform.sh`<br>
✅ Now visit [http://frontend.unstract.localhost](http://frontend.unstract.localhost) in your browser <br>
✅ Use user name and password `unstract` to login

That's all there is to it!

Another really quick way to experience Unstract is by signing up for our [hosted version](https://us-central-1.gcp.unstract.com/).

## ⏩ Quick Start Guide

Unstract comes well documented. You can get introduced to the [basics of Unstract](https://docs.unstract.com/), and [learn how to connect](https://docs.unstract.com/unstract_platform/setup_accounts/whats_needed) various systems like LLMs, Vector Databases, Embedding Models and Text Extractors to it. The easiest way to wet your feet is to go through our [Quick Start Guide](https://docs.unstract.com/unstract_platform/quick_start) where you actually get to do some prompt engineering in Prompt Studio and launch an API to structure varied credit card statements!

## 🤝 Ecosystem support

### LLM Providers
|| Provider | Status |
|---|---|---|
|<img src="docs/assets/3rd_party/openai.png" width="32"/>| OpenAI | ✅ Working |
|<img src="docs/assets/3rd_party/vertex_ai.png" width="32"/>| Google VertexAI, Gemini Pro | ✅ Working |
|<img src="docs/assets/3rd_party/azure_openai.png" width="32"/>| Azure OpenAI | ✅ Working  |
|<img src="docs/assets/3rd_party/palm.png" width="32"/>| Google PaLM | ✅ Working  |
|<img src="docs/assets/3rd_party/anyscale.png" width="32"/>| Anyscale | ✅ Working |
|<img src="docs/assets/3rd_party/replicate.png" width="32"/>| Replicate | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/anthropic.png" width="32"/>| Anthropic | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/mistral_ai.png" width="32"/>| Mistral AI | 🗓️ Coming soon! |

### Vector Databases
|| Provider | Status |
|---|---|---|
|<img src="docs/assets/3rd_party/qdrant.png" width="32"/>| Qdrant | ✅ Working |
|<img src="docs/assets/3rd_party/postgres.png" width="32"/>| PostgreSQL | ✅ Working |
|<img src="docs/assets/3rd_party/supabase.png" width="32"/>| Supabase | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/milvus.png" width="32"/>| Milvus | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/weaviate.png" width="32"/>| Weaviate | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/pinecone.png" width="32"/>| Pinecone | 🗓️ Coming soon! |

### Embeddings
|| Provider | Status |
|---|---|---|
|<img src="docs/assets/3rd_party/openai.png" width="32"/>| OpenAI | ✅ Working |
|<img src="docs/assets/3rd_party/azure_openai.png" width="32"/>| Azure OpenAI | ✅ Working  |
|<img src="docs/assets/3rd_party/palm.png" width="32"/>| Google PaLM | ✅ Working  |
|<img src="docs/assets/3rd_party/qdrant.png" width="32"/>| Qdrant | ✅ Working |
|<img src="docs/assets/3rd_party/huggingface.png" width="32"/>| Huggingface | 🗓️ Coming soon! |

### Text Extractors
|| Provider | Status |
|---|---|---|
|<img src="docs/assets/unstract_u_logo.png" width="32"/>| Unstract LLMWhisperer | ✅ Working |
|<img src="docs/assets/3rd_party/unstructured_io.png" width="32"/>| Unstructured.io Community | ✅ Working  |
|<img src="docs/assets/3rd_party/unstructured_io.png" width="32"/>| Unstructured.io Enterprise | ✅ Working  |
|<img src="docs/assets/3rd_party/llamaindex.png" width="32"/>| LlamaIndex Parse | 🗓️ Coming soon! |

### ETL Sources
|| Provider | Status |
|---|---|---|
|<img src="docs/assets/3rd_party/s3.png" width="32"/>| AWS S3 | ✅ Working |
|<img src="docs/assets/3rd_party/minio.png" width="32"/>| Minio | ✅ Working |
|<img src="docs/assets/3rd_party/dropbox.png" width="32"/>| Dropbox | ✅ Working |
|<img src="docs/assets/3rd_party/google_drive.png" width="32"/>| Google Drive | ✅ Working |
|<img src="docs/assets/3rd_party/box.png" width="32"/>| Box | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/gcp.png" width="32"/>| Google Cloud Storage | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/azure_openai.png" width="32"/>| Azure Cloud Storage | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/http.png" width="32"/>| HTTP/HTTPS | 🗓️ Coming soon! |

### ETL Destinations
|| Provider | Status |
|---|---|---|
|<img src="docs/assets/3rd_party/snowflake.png" width="32"/>| Snowflake | ✅ Working |
|<img src="docs/assets/3rd_party/amazon_redshift.png" width="32"/>| Amazon Redshift | ✅ Working |
|<img src="docs/assets/3rd_party/google_bigquery.png" width="32"/>| Google Bigquery | ✅ Working |
|<img src="docs/assets/3rd_party/postgres.png" width="32"/>| PostgreSQL | ✅ Working |
|<img src="docs/assets/3rd_party/mysql.png" width="32"/>| MySQL | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/mariadb.png" width="32"/>| MariaDB | 🗓️ Coming soon! |
|<img src="docs/assets/3rd_party/ms_sql.png" width="32"/>| Microsoft SQL Server | 🗓️ Coming soon! |

## 🙌 Contributing

Contributions are welcome! Please read [CONTRIBUTE.md](CONTRIBUTE.md) for further details on setting up the development environment, etc. It also points you to other detailed documents as needed.

## 👋 Join the LLM-powered automation community
