# JSON Schema Guide for Adapter UI

Reference for creating JSON schemas that generate adapter configuration UIs.

## Schema Structure

```json
{
  "title": "Provider Name Type",
  "type": "object",
  "required": ["field1", "field2"],
  "properties": { ... },
  "allOf": [ ... ]
}
```

## Field Types

### String Field

```json
{
  "field_name": {
    "type": "string",
    "title": "Display Label",
    "default": "default value",
    "description": "Help text shown to user"
  }
}
```

### Password Field

```json
{
  "api_key": {
    "type": "string",
    "title": "API Key",
    "format": "password",
    "description": "Your secret API key"
  }
}
```

### URL Field

```json
{
  "endpoint": {
    "type": "string",
    "title": "Endpoint URL",
    "format": "uri",
    "default": "https://api.example.com/v1"
  }
}
```

### Number Field

```json
{
  "timeout": {
    "type": "number",
    "title": "Timeout",
    "default": 300,
    "minimum": 0,
    "maximum": 3600,
    "multipleOf": 1,
    "description": "Timeout in seconds"
  }
}
```

### Integer Field

```json
{
  "max_retries": {
    "type": "integer",
    "title": "Max Retries",
    "default": 3,
    "minimum": 0,
    "maximum": 10
  }
}
```

### Boolean Field

```json
{
  "enable_feature": {
    "type": "boolean",
    "title": "Enable Feature",
    "default": false,
    "description": "Toggle to enable this feature"
  }
}
```

### Dropdown (Enum) Field

```json
{
  "model": {
    "type": "string",
    "title": "Model",
    "enum": ["model-a", "model-b", "model-c"],
    "default": "model-a",
    "description": "Select the model to use"
  }
}
```

### Multi-line Text

```json
{
  "json_credentials": {
    "type": "string",
    "title": "JSON Credentials",
    "format": "textarea",
    "description": "Paste your JSON credentials here"
  }
}
```

## Required Fields

Always include `adapter_name` as required:

```json
{
  "required": ["adapter_name", "api_key"],
  "properties": {
    "adapter_name": {
      "type": "string",
      "title": "Name",
      "default": "",
      "description": "Provide a unique name for this adapter instance"
    }
  }
}
```

## Conditional Fields

Show/hide fields based on other field values using `allOf` with `if`/`then`:

### Basic Conditional

```json
{
  "properties": {
    "auth_type": {
      "type": "string",
      "enum": ["api_key", "oauth"],
      "default": "api_key"
    }
  },
  "allOf": [
    {
      "if": {
        "properties": {
          "auth_type": { "const": "api_key" }
        }
      },
      "then": {
        "properties": {
          "api_key": {
            "type": "string",
            "format": "password",
            "title": "API Key"
          }
        },
        "required": ["api_key"]
      }
    },
    {
      "if": {
        "properties": {
          "auth_type": { "const": "oauth" }
        }
      },
      "then": {
        "properties": {
          "client_id": { "type": "string", "title": "Client ID" },
          "client_secret": { "type": "string", "format": "password" }
        },
        "required": ["client_id", "client_secret"]
      }
    }
  ]
}
```

### Boolean Toggle Conditional

```json
{
  "properties": {
    "enable_reasoning": {
      "type": "boolean",
      "default": false,
      "title": "Enable Reasoning"
    }
  },
  "allOf": [
    {
      "if": {
        "properties": {
          "enable_reasoning": { "const": true }
        }
      },
      "then": {
        "properties": {
          "reasoning_effort": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "default": "medium",
            "title": "Reasoning Effort"
          }
        },
        "required": ["reasoning_effort"]
      }
    },
    {
      "if": {
        "properties": {
          "enable_reasoning": { "const": false }
        }
      },
      "then": {
        "properties": {}
      }
    }
  ]
}
```

## Complete Examples

### Simple LLM Adapter Schema

```json
{
  "title": "Simple Provider LLM",
  "type": "object",
  "required": ["adapter_name", "api_key"],
  "properties": {
    "adapter_name": {
      "type": "string",
      "title": "Name",
      "default": "",
      "description": "Unique name for this adapter"
    },
    "api_key": {
      "type": "string",
      "title": "API Key",
      "format": "password"
    },
    "model": {
      "type": "string",
      "title": "Model",
      "default": "default-model"
    },
    "max_tokens": {
      "type": "number",
      "minimum": 0,
      "title": "Max Tokens"
    },
    "timeout": {
      "type": "number",
      "minimum": 0,
      "default": 900,
      "title": "Timeout (seconds)"
    }
  }
}
```

### Cloud Provider with Regions

```json
{
  "title": "Cloud Provider LLM",
  "type": "object",
  "required": ["adapter_name", "api_key", "region"],
  "properties": {
    "adapter_name": {
      "type": "string",
      "title": "Name"
    },
    "api_key": {
      "type": "string",
      "format": "password",
      "title": "API Key"
    },
    "region": {
      "type": "string",
      "title": "Region",
      "enum": ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"],
      "default": "us-east-1"
    },
    "model": {
      "type": "string",
      "title": "Model",
      "enum": ["model-small", "model-medium", "model-large"],
      "default": "model-medium"
    }
  }
}
```

### Azure-Style with Deployment

```json
{
  "title": "Azure-Style Provider",
  "type": "object",
  "required": ["adapter_name", "api_key", "azure_endpoint", "deployment_name"],
  "properties": {
    "adapter_name": {
      "type": "string",
      "title": "Name"
    },
    "azure_endpoint": {
      "type": "string",
      "format": "uri",
      "title": "Endpoint",
      "description": "Your Azure endpoint URL"
    },
    "api_key": {
      "type": "string",
      "format": "password",
      "title": "API Key"
    },
    "deployment_name": {
      "type": "string",
      "title": "Deployment Name",
      "description": "Name of your model deployment"
    },
    "api_version": {
      "type": "string",
      "title": "API Version",
      "default": "2024-02-01"
    }
  }
}
```

### Self-Hosted (Ollama-Style)

```json
{
  "title": "Self-Hosted LLM",
  "type": "object",
  "required": ["adapter_name", "base_url"],
  "properties": {
    "adapter_name": {
      "type": "string",
      "title": "Name"
    },
    "base_url": {
      "type": "string",
      "format": "uri",
      "title": "Server URL",
      "default": "http://localhost:11434",
      "description": "URL of your local server"
    },
    "model": {
      "type": "string",
      "title": "Model",
      "default": "llama2",
      "description": "Model name (must be pulled on server)"
    }
  }
}
```

### Embedding Adapter Schema

```json
{
  "title": "Provider Embedding",
  "type": "object",
  "required": ["adapter_name", "api_key"],
  "properties": {
    "adapter_name": {
      "type": "string",
      "title": "Name"
    },
    "model": {
      "type": "string",
      "title": "Model",
      "default": "text-embedding-model"
    },
    "api_key": {
      "type": "string",
      "format": "password",
      "title": "API Key"
    },
    "api_base": {
      "type": "string",
      "format": "uri",
      "title": "API Base URL"
    },
    "embed_batch_size": {
      "type": "number",
      "minimum": 1,
      "default": 10,
      "title": "Batch Size"
    },
    "timeout": {
      "type": "number",
      "minimum": 0,
      "default": 240,
      "title": "Timeout (seconds)"
    }
  }
}
```

### Embedding with Dimensions

```json
{
  "title": "OpenAI Embedding",
  "type": "object",
  "required": ["adapter_name", "api_key"],
  "properties": {
    "adapter_name": {
      "type": "string",
      "title": "Name"
    },
    "model": {
      "type": "string",
      "title": "Model",
      "default": "text-embedding-3-small",
      "description": "text-embedding-3-small/large support custom dimensions"
    },
    "api_key": {
      "type": "string",
      "format": "password",
      "title": "API Key"
    },
    "dimensions": {
      "type": "number",
      "minimum": 1,
      "multipleOf": 1,
      "title": "Dimensions",
      "description": "Output dimensions (only for text-embedding-3-* models)"
    }
  }
}
```

### Reasoning with Effort Control (Mistral Magistral, OpenAI o1/o3)

```json
{
  "properties": {
    "enable_reasoning": {
      "type": "boolean",
      "title": "Enable Reasoning",
      "default": false,
      "description": "Enable reasoning for Magistral models"
    }
  },
  "allOf": [
    {
      "if": {
        "properties": { "enable_reasoning": { "const": true } }
      },
      "then": {
        "properties": {
          "reasoning_effort": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "default": "medium",
            "title": "Reasoning Effort"
          }
        },
        "required": ["reasoning_effort"]
      }
    }
  ]
}
```

### Optional Credentials (AWS Bedrock)

```json
{
  "title": "Bedrock LLM",
  "type": "object",
  "required": ["adapter_name", "region_name", "model"],
  "properties": {
    "adapter_name": { "type": "string", "title": "Name" },
    "model": { "type": "string", "title": "Model" },
    "region_name": { "type": "string", "title": "AWS Region" },
    "aws_access_key_id": {
      "type": "string",
      "format": "password",
      "title": "AWS Access Key ID",
      "description": "Leave empty if using AWS Profile or IAM role."
    },
    "aws_secret_access_key": {
      "type": "string",
      "format": "password",
      "title": "AWS Secret Access Key",
      "description": "Leave empty if using AWS Profile or IAM role."
    },
    "aws_profile_name": {
      "type": "string",
      "title": "AWS Profile Name",
      "description": "AWS SSO profile name for authentication."
    }
  }
}
```

### JSON Mode Toggle (Ollama)

```json
{
  "properties": {
    "json_mode": {
      "type": "boolean",
      "title": "JSON Mode",
      "default": false,
      "description": "Constrain output to valid JSON"
    }
  }
}
```

## Best Practices

1. **Always include `adapter_name`** as required field
2. **Use `format: "password"`** for secrets and API keys
3. **Provide sensible defaults** for optional fields
4. **Add descriptions** for non-obvious fields
5. **Use enums** when choices are limited
6. **Keep titles short** - they become form labels
7. **Order properties** by importance/usage frequency
8. **Use conditional fields** to reduce clutter
9. **Validate with JSON Schema validator** before deploying
10. **Make credentials optional** when multiple auth methods exist
