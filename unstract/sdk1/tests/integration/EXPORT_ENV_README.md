# Environment Variable Export Guide

## Problem

The standard approach of exporting environment variables from `.env.test` fails when the file contains inline comments:

```bash
export $(grep -v '^#' .env.test | xargs)
# Error: xargs: unmatched double quote
# Error: bash: export: `#': not a valid identifier
```

This happens because lines like:
```bash
QDRANT_API_KEY="eyJhbGci..."  # Optional for local setup
```

The `#` after the quoted value causes `xargs` to split the line incorrectly.

## Solution

Use the provided `export_env.sh` script that properly handles inline comments and quoted values.

## Usage

### Method 1: Source the Script (Recommended)

Source the script to load the `export_env_from_file` function, then call it:

```bash
cd unstract/sdk1/tests/integration
source export_env.sh
export_env_from_file
```

This exports all variables from `.env.test` into your current shell session.

### Method 2: Execute Directly

Run the script directly to export variables:

```bash
cd unstract/sdk1/tests/integration
./export_env.sh
```

Note: This method only works if you source the script's output or run it in a subshell.

### Method 3: One-Liner for pytest

The cleanest way to run tests with environment variables:

```bash
cd unstract/sdk1/tests/integration
source export_env.sh && export_env_from_file && pytest test_vector_db.py -v
```

### Method 4: Custom .env File

Export from a different file:

```bash
source export_env.sh
export_env_from_file /path/to/custom.env
```

## What It Does

The script:
1. **Skips comment-only lines**: Lines starting with `#` are ignored
2. **Removes inline comments**: `KEY="value"  # comment` → exports `KEY="value"`
3. **Handles quoted values**: Properly preserves values with spaces, special characters
4. **Handles unquoted values**: Works with both `KEY=value` and `KEY="value"` formats

## Examples

### Before (Fails)
```bash
export $(grep -v '^#' .env.test | xargs)
# xargs: unmatched double quote
# bash: export: `#': not a valid identifier
```

### After (Works)
```bash
source export_env.sh && export_env_from_file
# Environment variables exported from .env.test
```

### Verify Exports
```bash
source export_env.sh && export_env_from_file
echo $QDRANT_URL
echo $QDRANT_API_KEY
env | grep QDRANT
```

## Integration with Tests

### Running VectorDB Tests
```bash
source export_env.sh && export_env_from_file && pytest test_vector_db.py -v
```

### Running X2Text Tests
```bash
source export_env.sh && export_env_from_file && pytest test_x2text.py -v
```

### Running All Integration Tests
```bash
source export_env.sh && export_env_from_file && pytest -v
```

## Technical Details

### Line Processing

The script uses bash regex matching to handle different formats:

1. **Quoted values with inline comments**:
   ```bash
   KEY="value"  # comment
   ```
   Extracts: `KEY=value`

2. **Unquoted values with inline comments**:
   ```bash
   KEY=value  # comment
   ```
   Extracts: `KEY=value`

3. **Values without comments**:
   ```bash
   KEY="value"
   KEY=value
   ```
   Exports as-is

### Supported Formats

✅ **Supported**:
```bash
# Comment-only lines (skipped)
SIMPLE=value
QUOTED="value with spaces"
WITH_COMMENT=value  # inline comment
QUOTED_WITH_COMMENT="value"  # inline comment
EMPTY_VALUE=""
SPECIAL_CHARS="!@#$%^&*()"
MULTI_WORD="hello world"  # description
```

❌ **Not Supported**:
```bash
export KEY=value  # 'export' keyword should be removed
KEY = value  # spaces around = not supported
KEY='single quotes'  # use double quotes
```

## Alternative Approaches

### Using python-dotenv (Recommended for Tests)

The `conftest.py` file already loads `.env.test` automatically:

```python
from dotenv import load_dotenv
load_dotenv('.env.test')
```

This is the preferred method for pytest and already works in the integration tests.

### Using direnv

For automatic loading on directory change:

1. Install direnv: `sudo apt install direnv`
2. Create `.envrc`:
   ```bash
   source_env .env.test
   ```
3. Run: `direnv allow`

### Using set -a

Traditional bash approach (careful - exports ALL variables):

```bash
set -a  # Auto-export all variables
source <(grep -v '^#' .env.test | sed 's/#.*//')
set +a  # Disable auto-export
```

## Troubleshooting

### Script Not Found
```bash
chmod +x export_env.sh
./export_env.sh
```

### Variables Not Exporting
Make sure to **source** the script, don't just execute it:
```bash
# Wrong
./export_env.sh

# Correct
source export_env.sh && export_env_from_file
```

### Checking What Got Exported
```bash
source export_env.sh && export_env_from_file
env | grep -E "QDRANT|OPENAI|ANTHROPIC"
```

### Clearing Exported Variables
```bash
unset QDRANT_URL QDRANT_API_KEY OPENAI_API_KEY
# Or start a new shell session
```

## Best Practices

1. **Use conftest.py for pytest**: The automatic loading via `python-dotenv` is cleaner
2. **Use export_env.sh for shell commands**: When running non-pytest commands
3. **Never commit .env.test**: It's already gitignored
4. **Keep .env.test.sample updated**: Document all required variables
5. **Use update_env.py**: Merge sample updates without losing credentials

## See Also

- [ENV_UPDATE_README.md](./ENV_UPDATE_README.md) - Smart .env.test updater
- [.env.test.sample](./.env.test.sample) - Template for environment variables
- [conftest.py](./conftest.py) - Pytest auto-loader for .env.test
