# JSON Schema Examples Reference

Examples of JSON schemas for different connector authentication patterns.

## Basic Schema Structure

All connector schemas follow this base structure:

```json
{
  "title": "Connector Display Name",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector",
          "description": "A unique name to identify this connector instance"
        }
      }
    },
    {
      // Authentication and connection options here
    }
  ]
}
```

---

## Pattern: URL vs Individual Parameters (Database)

Used by: PostgreSQL, MySQL, MariaDB, Redshift

```json
{
  "title": "PostgreSQL Database",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "oneOf": [
        {
          "title": "Connection URL",
          "required": ["connection_url"],
          "properties": {
            "connection_url": {
              "type": "string",
              "title": "Connection URL",
              "description": "postgresql://username:password@localhost:5432/database",
              "format": "uri"
            }
          }
        },
        {
          "title": "Connection Parameters",
          "required": ["host", "port", "database", "user", "password"],
          "properties": {
            "host": {
              "type": "string",
              "title": "Host",
              "description": "Database server hostname"
            },
            "port": {
              "type": "string",
              "title": "Port",
              "default": "5432"
            },
            "database": {
              "type": "string",
              "title": "Database",
              "description": "Database name"
            },
            "schema": {
              "type": "string",
              "title": "Schema",
              "default": "public"
            },
            "user": {
              "type": "string",
              "title": "User"
            },
            "password": {
              "type": "string",
              "title": "Password",
              "format": "password"
            }
          }
        }
      ]
    }
  ]
}
```

---

## Pattern: OAuth Authentication (Filesystem)

Used by: Google Drive, Dropbox, Box, OneDrive

```json
{
  "title": "Google Drive",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "required": ["access_token", "refresh_token"],
      "properties": {
        "access_token": {
          "type": "string",
          "title": "Access Token",
          "description": "OAuth access token (auto-populated)",
          "format": "password"
        },
        "refresh_token": {
          "type": "string",
          "title": "Refresh Token",
          "description": "OAuth refresh token (auto-populated)",
          "format": "password"
        },
        "token_expiry": {
          "type": "string",
          "title": "Token Expiry",
          "description": "Token expiration timestamp"
        }
      }
    }
  ]
}
```

---

## Pattern: API Key Authentication

Used by: Many cloud services

```json
{
  "title": "Service Name",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "required": ["api_key"],
      "properties": {
        "api_key": {
          "type": "string",
          "title": "API Key",
          "description": "Your API key from the service dashboard",
          "format": "password"
        },
        "region": {
          "type": "string",
          "title": "Region",
          "description": "Service region",
          "enum": ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"],
          "default": "us-east-1"
        }
      }
    }
  ]
}
```

---

## Pattern: Service Account (GCP)

Used by: BigQuery, Google Cloud Storage

```json
{
  "title": "BigQuery",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "oneOf": [
        {
          "title": "Service Account JSON",
          "required": ["service_account_json"],
          "properties": {
            "service_account_json": {
              "type": "string",
              "title": "Service Account JSON",
              "description": "Paste the entire service account JSON key file contents",
              "format": "textarea"
            }
          }
        },
        {
          "title": "Service Account File Path",
          "required": ["service_account_path"],
          "properties": {
            "service_account_path": {
              "type": "string",
              "title": "Service Account Path",
              "description": "Path to service account JSON file"
            }
          }
        }
      ]
    },
    {
      "required": ["project_id"],
      "properties": {
        "project_id": {
          "type": "string",
          "title": "Project ID",
          "description": "GCP Project ID"
        },
        "dataset": {
          "type": "string",
          "title": "Dataset",
          "description": "BigQuery dataset name"
        }
      }
    }
  ]
}
```

---

## Pattern: Access Key + Secret (AWS/S3)

Used by: S3, Minio, Azure Blob

```json
{
  "title": "Minio / S3",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "required": ["access_key", "secret_key", "endpoint_url", "bucket"],
      "properties": {
        "access_key": {
          "type": "string",
          "title": "Access Key",
          "description": "S3 Access Key ID"
        },
        "secret_key": {
          "type": "string",
          "title": "Secret Key",
          "description": "S3 Secret Access Key",
          "format": "password"
        },
        "endpoint_url": {
          "type": "string",
          "title": "Endpoint URL",
          "description": "S3-compatible endpoint URL",
          "default": "https://s3.amazonaws.com"
        },
        "bucket": {
          "type": "string",
          "title": "Bucket",
          "description": "S3 bucket name"
        },
        "region": {
          "type": "string",
          "title": "Region",
          "default": "us-east-1"
        }
      }
    }
  ]
}
```

---

## Pattern: Username + Password + Host (Basic)

Used by: SFTP, FTP, basic databases

```json
{
  "title": "SFTP",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "required": ["host", "username"],
      "properties": {
        "host": {
          "type": "string",
          "title": "Host",
          "description": "SFTP server hostname"
        },
        "port": {
          "type": "integer",
          "title": "Port",
          "default": 22
        },
        "username": {
          "type": "string",
          "title": "Username"
        }
      }
    },
    {
      "oneOf": [
        {
          "title": "Password Authentication",
          "required": ["password"],
          "properties": {
            "password": {
              "type": "string",
              "title": "Password",
              "format": "password"
            }
          }
        },
        {
          "title": "Key Authentication",
          "required": ["private_key"],
          "properties": {
            "private_key": {
              "type": "string",
              "title": "Private Key",
              "description": "SSH private key contents",
              "format": "textarea"
            },
            "passphrase": {
              "type": "string",
              "title": "Key Passphrase",
              "format": "password"
            }
          }
        }
      ]
    }
  ]
}
```

---

## Pattern: Multiple Auth Methods (Snowflake)

Used by: Snowflake (supports password, key-pair, OAuth, SSO)

```json
{
  "title": "Snowflake",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "required": ["account", "warehouse", "database", "schema", "user"],
      "properties": {
        "account": {
          "type": "string",
          "title": "Account",
          "description": "Snowflake account identifier (e.g., xyz12345.us-east-1)"
        },
        "warehouse": {
          "type": "string",
          "title": "Warehouse"
        },
        "database": {
          "type": "string",
          "title": "Database"
        },
        "schema": {
          "type": "string",
          "title": "Schema",
          "default": "PUBLIC"
        },
        "user": {
          "type": "string",
          "title": "User"
        },
        "role": {
          "type": "string",
          "title": "Role",
          "description": "Optional role to use"
        }
      }
    },
    {
      "oneOf": [
        {
          "title": "Password Authentication",
          "required": ["password"],
          "properties": {
            "password": {
              "type": "string",
              "title": "Password",
              "format": "password"
            }
          }
        },
        {
          "title": "Key-Pair Authentication",
          "required": ["private_key"],
          "properties": {
            "private_key": {
              "type": "string",
              "title": "Private Key",
              "description": "RSA private key (PEM format)",
              "format": "textarea"
            },
            "private_key_passphrase": {
              "type": "string",
              "title": "Key Passphrase",
              "format": "password"
            }
          }
        },
        {
          "title": "External Browser (SSO)",
          "properties": {
            "authenticator": {
              "type": "string",
              "title": "Authenticator",
              "const": "externalbrowser",
              "default": "externalbrowser"
            }
          }
        }
      ]
    }
  ]
}
```

---

## Pattern: Connection String Only

Used by: Some legacy systems, Redis, MongoDB

```json
{
  "title": "MongoDB",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "required": ["connection_string"],
      "properties": {
        "connection_string": {
          "type": "string",
          "title": "Connection String",
          "description": "mongodb://username:password@host:27017/database",
          "format": "password"
        },
        "database": {
          "type": "string",
          "title": "Database",
          "description": "Default database (overrides connection string)"
        }
      }
    }
  ]
}
```

---

## Pattern: With SSL/TLS Options

Add SSL options to any schema:

```json
{
  "properties": {
    "sslEnabled": {
      "type": "boolean",
      "title": "Enable SSL/TLS",
      "default": false
    }
  },
  "dependencies": {
    "sslEnabled": {
      "oneOf": [
        {
          "properties": {
            "sslEnabled": { "const": false }
          }
        },
        {
          "properties": {
            "sslEnabled": { "const": true },
            "sslMode": {
              "type": "string",
              "title": "SSL Mode",
              "enum": ["require", "verify-ca", "verify-full"],
              "default": "require"
            },
            "sslCert": {
              "type": "string",
              "title": "SSL Certificate",
              "description": "Client certificate (PEM)",
              "format": "textarea"
            },
            "sslKey": {
              "type": "string",
              "title": "SSL Key",
              "description": "Client private key (PEM)",
              "format": "textarea"
            },
            "sslCA": {
              "type": "string",
              "title": "SSL CA Certificate",
              "description": "CA certificate for verification (PEM)",
              "format": "textarea"
            }
          }
        }
      ]
    }
  }
}
```

---

## Field Format Reference

| Format | UI Rendering |
|--------|--------------|
| `password` | Masked input field |
| `textarea` | Multi-line text area |
| `uri` | URL input with validation |
| `email` | Email input with validation |
| `date` | Date picker |
| `date-time` | DateTime picker |

## Type Reference

| Type | JSON Schema Type |
|------|------------------|
| Text | `"type": "string"` |
| Number | `"type": "integer"` or `"type": "number"` |
| Boolean | `"type": "boolean"` |
| Dropdown | `"type": "string", "enum": [...]` |
| Hidden | Add `"x-hidden": true` |
