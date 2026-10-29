/*
 * The design's brand marks as URLs, keyed for lookup. The SVGs were exported
 * from the 2026-10-09 Figma exports: provider marks from the "Logo · …"
 * components on "12 · LLMs" (node 1407:2), product marks from the Product
 * Switcher file (node 51:1401). Flags are cloud's region-selector SVGs.
 *
 * Rendered as <img>, not inline, so 37 SVGs cost no JavaScript.
 */

import euFlag from "./flags/eu.svg";
import usFlag from "./flags/us.svg";
import documentStudioProduct from "./logos/products/document-studio.svg";
import flowProduct from "./logos/products/flow.svg";
import llmwhispererProduct from "./logos/products/llmwhisperer.svg";
import amazonS3 from "./logos/providers/amazon-s3.svg";
import anthropic from "./logos/providers/anthropic.svg";
import anyscale from "./logos/providers/anyscale.svg";
import awsBedrock from "./logos/providers/aws-bedrock.svg";
import azureCloudStorage from "./logos/providers/azure-cloud-storage.svg";
import azureOpenai from "./logos/providers/azure-openai.svg";
import bigquery from "./logos/providers/bigquery.svg";
import dropbox from "./logos/providers/dropbox.svg";
import gemini from "./logos/providers/gemini.svg";
import googleCloud from "./logos/providers/google-cloud.svg";
import googleDrive from "./logos/providers/google-drive.svg";
import llamaparse from "./logos/providers/llamaparse.svg";
import mariadb from "./logos/providers/mariadb.svg";
import milvus from "./logos/providers/milvus.svg";
import minimax from "./logos/providers/minimax.svg";
import mistral from "./logos/providers/mistral.svg";
import mssql from "./logos/providers/mssql.svg";
import mysql from "./logos/providers/mysql.svg";
import nvidia from "./logos/providers/nvidia.svg";
import ollama from "./logos/providers/ollama.svg";
import openai from "./logos/providers/openai.svg";
import openrouter from "./logos/providers/openrouter.svg";
import pinecone from "./logos/providers/pinecone.svg";
import postgresql from "./logos/providers/postgresql.svg";
import qdrant from "./logos/providers/qdrant.svg";
import redshift from "./logos/providers/redshift.svg";
import sftp from "./logos/providers/sftp.svg";
import sharepoint from "./logos/providers/sharepoint.svg";
import snowflake from "./logos/providers/snowflake.svg";
import unstract from "./logos/providers/unstract.svg";
import unstructuredIo from "./logos/providers/unstructured-io.svg";
import weaviate from "./logos/providers/weaviate.svg";

export type BrandMark = Readonly<{
  src: string;
  /** One dark ink with no tile of its own: invert it on the dark theme. */
  mono?: boolean;
}>;

const mark = (src: string): BrandMark => ({ src });
const monoMark = (src: string): BrandMark => ({ src, mono: true });

/**
 * Keyed on the provider key: the part of an adapter or connector id before
 * `|` (`openai|502ecf49-…` → `openai`). The LLM and embedding adapters of one
 * vendor share a key. Keys missing here fall back to the API's icon URL.
 */
export const PROVIDER_MARKS: Readonly<Record<string, BrandMark>> = {
  openai: monoMark(openai),
  anthropic: monoMark(anthropic),
  azureopenai: mark(azureOpenai),
  bedrock: mark(awsBedrock),
  gemini: mark(gemini),
  minimax: mark(minimax),
  mistral: mark(mistral),
  nvidiabuild: mark(nvidia),
  ollama: monoMark(ollama),
  openrouter: mark(openrouter),
  vertexai: mark(googleCloud),
  anyscale: mark(anyscale),
  milvus: mark(milvus),
  pinecone: monoMark(pinecone),
  postgres: mark(postgresql),
  qdrant: mark(qdrant),
  weaviate: mark(weaviate),
  llmwhisperer: mark(unstract),
  llamaparse: mark(llamaparse),
  unstructuredcommunity: mark(unstructuredIo),
  unstructuredenterprise: mark(unstructuredIo),
  googledocumentai: mark(googleCloud),
  bigquery: mark(bigquery),
  mariadb: mark(mariadb),
  mssql: mark(mssql),
  mysql: mark(mysql),
  postgresql: mark(postgresql),
  redshift: mark(redshift),
  snowflake: mark(snowflake),
  azure_cloud_storage: mark(azureCloudStorage),
  dropbox: mark(dropbox),
  gdrive: mark(googleDrive),
  google_cloud_storage: mark(googleCloud),
  minio: mark(amazonS3),
  pcs: mark(unstract),
  sftp: mark(sftp),
  sharepoint: mark(sharepoint),
};

export type Product = "document-studio" | "flow" | "llmwhisperer";

export const PRODUCT_MARKS: Readonly<Record<Product, BrandMark>> = {
  "document-studio": mark(documentStudioProduct),
  flow: mark(flowProduct),
  llmwhisperer: mark(llmwhispererProduct),
};

export type Region = "us" | "eu";

export const REGION_FLAGS: Readonly<Record<Region, BrandMark>> = {
  us: mark(usFlag),
  eu: mark(euFlag),
};
