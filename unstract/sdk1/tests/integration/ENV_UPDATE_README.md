# Environment File Update Guide

## Quick Start

To update your `.env.test` file with new variables from `.env.test.sample` while preserving your existing values:

```bash
python update_env.py
```

Or if executable:

```bash
./update_env.py
```

## What It Does

The `update_env.py` script intelligently merges `.env.test.sample` (template) with your existing `.env.test`:

✅ **Preserves** all your existing environment variable values
✅ **Adds** any new variables from the updated sample file
✅ **Updates** comments and structure from the sample
✅ **Creates** automatic backup before making changes
✅ **Maintains** the organization and sections from the sample

## Example

### Before Update

**Your .env.test:**
```bash
# Old configuration
OPENAI_API_KEY="sk-your-actual-key-123"
ANTHROPIC_API_KEY="sk-ant-your-key-456"
```

**Updated .env.test.sample:**
```bash
# ============================================================================
# OpenAI Configuration
# ============================================================================
OPENAI_API_KEY="your-openai-api-key"
OPENAI_MODEL="gpt-4o-mini"

# ============================================================================
# Anthropic Configuration
# ============================================================================
ANTHROPIC_API_KEY="your-anthropic-api-key"
ANTHROPIC_MODEL="claude-sonnet-4-20250514"

# ============================================================================
# New X2Text Configuration (NEW!)
# ============================================================================
LLAMA_PARSE_API_KEY="your-llama-parse-api-key"
```

### After Running `update_env.py`

**Your updated .env.test:**
```bash
# ============================================================================
# OpenAI Configuration
# ============================================================================
OPENAI_API_KEY="sk-your-actual-key-123"  # Your value preserved!
OPENAI_MODEL="gpt-4o-mini"  # New variable added

# ============================================================================
# Anthropic Configuration
# ============================================================================
ANTHROPIC_API_KEY="sk-ant-your-key-456"  # Your value preserved!
ANTHROPIC_MODEL="claude-sonnet-4-20250514"  # New variable added

# ============================================================================
# New X2Text Configuration (NEW!)
# ============================================================================
LLAMA_PARSE_API_KEY="your-llama-parse-api-key"  # New section added
```

## Output Example

```
🔄 Smart .env.test Updater
============================================================
📦 Creating backup: .env.test.backup.20251103_165430
🔀 Merging .env.test.sample with existing values...
✅ Updated .env.test

📊 Summary:
   • Preserved existing values: 15
   • Added new variables: 8
   • Total variables: 23

💾 Backup saved: .env.test.backup.20251103_165430

✨ Done! Your .env.test has been updated.
   Review the changes and update any new variables with your actual values.
```

## Safety Features

### Automatic Backups
Every time you run the script, it creates a timestamped backup:
- Format: `.env.test.backup.YYYYMMDD_HHMMSS`
- Example: `.env.test.backup.20251103_165430`
- Located in the same directory as `.env.test`

### Non-Destructive
- Never modifies your existing values
- Only adds new variables from the sample
- Preserves comments and structure

## Manual Workflow (Alternative)

If you prefer manual control:

1. **Backup your current file:**
   ```bash
   cp .env.test .env.test.backup
   ```

2. **Copy sample to .env.test:**
   ```bash
   cp .env.test.sample .env.test
   ```

3. **Manually restore your values:**
   - Open `.env.test` and `.env.test.backup` side by side
   - Copy your actual API keys and credentials from backup to new file

⚠️ **Not recommended** - the script automates this and prevents mistakes!

## After Updating

1. **Review new variables:**
   ```bash
   diff .env.test.backup.* .env.test
   ```

2. **Fill in new credentials:**
   - Open `.env.test`
   - Look for new variables with placeholder values
   - Update with your actual credentials

3. **Test your configuration:**
   ```bash
   pytest test_llm.py --collect-only  # Verify providers are detected
   ```

## Troubleshooting

### Script Errors

**"❌ Error: .env.test.sample not found!"**
- Ensure you're in the `unstract/sdk1/tests/integration/` directory
- Verify `.env.test.sample` exists in the same directory

**Permission denied**
```bash
chmod +x update_env.py
```

### Check What Changed

View differences between backup and updated file:
```bash
# Find most recent backup
ls -lt .env.test.backup.* | head -1

# Compare with current
diff .env.test.backup.20251103_165430 .env.test
```

### Restore from Backup

If something went wrong:
```bash
# List available backups
ls -lt .env.test.backup.*

# Restore from specific backup
cp .env.test.backup.20251103_165430 .env.test
```

## Best Practices

1. **Run after pulling updates:**
   ```bash
   git pull origin main
   cd unstract/sdk1/tests/integration
   python update_env.py
   ```

2. **Review changes before committing:**
   - Never commit `.env.test` (it's gitignored)
   - Only commit `.env.test.sample` changes
   - Keep your credentials secure

3. **Clean up old backups periodically:**
   ```bash
   # Keep only last 5 backups
   ls -t .env.test.backup.* | tail -n +6 | xargs rm -f
   ```

## Integration with Git Workflow

The script is safe to use in your development workflow:

```bash
# After pulling latest changes
git pull origin main

# Update your .env.test with new variables
cd unstract/sdk1/tests/integration
python update_env.py

# Review what was added
git diff .env.test.sample

# Your .env.test is updated, .env.test.sample changes are visible in git
git status
```

## Script Logic

The merge algorithm:
1. Reads all existing key-value pairs from `.env.test`
2. Processes `.env.test.sample` line by line:
   - **Comments & empty lines**: Copied from sample (latest structure)
   - **Existing variables**: Uses your current value
   - **New variables**: Adds from sample with placeholder value
3. Writes merged output to `.env.test`
4. Creates timestamped backup before any changes

This ensures:
- Your credentials are never lost
- New configuration options are added
- Documentation/comments stay current
- File structure matches the latest template
