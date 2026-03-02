# DamnGood MCP Manager

A centralized CLI tool to manage Model Context Protocol (MCP) servers across multiple AI coding assistants.

## The Problem

Managing MCP servers across different AI tools (Cursor, Claude, Gemini, OpenCode) is painful. You have to:
- Add the same server to each tool individually
- Keep configurations in sync manually
- Edit different JSON files in different locations

## The Solution

DamnGood MCP Manager provides **centralized management**:
1. Store your MCP servers in one central registry
2. Assign each server to the AI tools you want to use it with
3. Sync once to push configs to all tools automatically

## Supported Clients

Auto-discovered clients:
- **Cursor** - `~/.cursor/mcp.json`
- **Claude** (Code & Desktop) - `~/.claude.json`
- **Gemini CLI** - `~/.gemini/settings.json`
- **OpenCode** - `~/.config/opencode/opencode.json`

Plus register any custom MCP-compatible tool.

## Install

```bash
# Clone the repo
git clone https://github.com/5LV10/damngood.git
cd damngood

# Install in editable mode (for development)
pip install -e .

# Or install normally
pip install .

# All set!
damngood --help
```

## Quick Start

```bash
# Auto-discovers your installed AI tools
damngood client list

# Import existing configs from your tools
damngood import

# Or add a new mcp server
damngood add filesystem

# Sync to all assigned clients
damngood sync
```

## How It Works

### Central Registry

All your MCP servers are stored in `~/.damngood/registry.json`:

```json
{
  "servers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "env": {},
      "clients": ["cursor", "gemini"],
      "created_at": "2025-02-12T10:00:00",
      "updated_at": "2025-02-12T10:00:00"
    }
  }
}
```

The `clients` array determines which AI tools get this server on sync.

### Client Registry

Your AI tools are tracked in `~/.damngood/clients.json`:

```json
{
  "clients": {
    "cursor": {
      "name": "cursor",
      "path": "/home/user/.cursor/mcp.json",
      "key": "mcpServers",
      "auto_discovered": true,
      "enabled": true
    }
  }
}
```

Auto-discovered clients are found by checking if their config files exist.

## Usage

### Two Modes of Operation

**Central Mode (Default)** - Manage servers centrally across all clients:
```bash
damngood list
damngood add myserver
damngood sync
```

**Client Mode** - Manage a single client's servers directly:
```bash
damngood --client cursor list
damngood --client cursor add myserver --command npx
```

### Client Management

```bash
# List discovered and registered clients
damngood client list

# Register a custom tool
damngood client register windsurf --path ~/.windsurf/mcp.json

# Disable a client (won't receive syncs)
damngood client disable gemini

# Remove a custom registration
damngood client remove windsurf
```

### Central Registry Commands

```bash
# List all centrally managed servers
damngood list

# Add a server (opens $EDITOR with JSON template)
damngood add filesystem
# Editor opens with:
# {
#   "type": "stdio",
#   "command": "npx",
#   "args": [],
#   "env": {},
#   "clients": []
# }
# Fill it out, save, close.

# Edit an existing server
damngood edit filesystem

# Show server details
damngood show filesystem

# Remove from central registry
damngood remove filesystem

# Sync to all assigned clients
damngood sync

# Import existing configs (prompts per-server)
damngood import
```

### JSON Editing

When you run `damngood add <name>` or `damngood edit <name>`, your default editor opens:

- Uses `$EDITOR` environment variable
- Falls back to: nano → vim → vi
- Validates JSON when you save
- Aborts if you close without saving

Example workflow:
```bash
$ damngood add github
# nano opens with template...
# Edit to:
# {
#   "type": "stdio",
#   "command": "npx",
#   "args": ["-y", "@modelcontextprotocol/server-github"],
#   "env": {"GITHUB_TOKEN": "your-token"},
#   "clients": ["cursor", "claude"]
# }
# Save and exit nano
Added server 'github' to central registry

$ damngood sync
Syncing 1 server(s) to 2 client(s)...
Syncing to cursor...
  Synced 1 server(s) to /home/user/.cursor/mcp.json
Syncing to claude...
  Synced 1 server(s) to /home/user/.claude/config.json
Sync complete!
```

### Import Existing Configs

```bash
$ damngood import

Found server 'slack' in cursor
Import? [y]es / [n]o / [s]kip all: y
  Imported 'slack'

Found server 'postgres' in gemini
Import? [y]es / [n]o / [s]kip all: y
  Imported 'postgres'

Imported 2 server(s): slack, postgres
Run 'damngood sync' to push to all clients
```

## Workflow Examples

### Setting up a new server across multiple tools

```bash
# 1. Check your clients
$ damngood client list
Registered Clients:
----------------------------------------------------------------------
Name            Status     Auto   Config Path
----------------------------------------------------------------------
cursor          enabled    yes    /home/user/.cursor/mcp.json
gemini          enabled    yes    /home/user/.gemini/settings.json
opencode        enabled    yes    /home/user/.config/opencode/opencode.json

# 2. Add server via editor
$ damngood add filesystem
# (editor opens, fill in details, set clients: ["cursor", "gemini"])

# 3. Sync to assigned clients
$ damngood sync
Syncing 1 server(s) to 2 client(s)...
Syncing to cursor...
  Synced 1 server(s) to /home/user/.cursor/mcp.json
Syncing to gemini...
  Synced 1 server(s) to /home/user/.gemini/settings.json
Sync complete!

# 4. Verify
$ damngood list
Centrally Managed Servers:
----------------------------------------------------------------------
Name                 Command                        Clients
----------------------------------------------------------------------
filesystem           npx -y @modelcontextpro...     cursor, gemini
```

### Managing existing setups

```bash
# Import what you already have
$ damngood import
Found server 'old-server' in cursor
Import? [y]es / [n]o / [s]kip all: y
  Imported 'old-server'

# Now it's in central registry
$ damngood show old-server
Server: old-server
----------------------------------------
Type: stdio
Command: npx
Args: ['-y', 'some-package']
Env: {}
Clients: ['cursor']

# Add another client to this server
$ damngood edit old-server
# (change clients to ["cursor", "gemini"])

# Sync to update all clients
$ damngood sync
```

### Single-client mode

Sometimes you want to manage just one tool:

```bash
# View only Cursor's servers
$ damngood --client cursor list
Configured MCP Servers (cursor):
------------------------------------------------------------
  filesystem           [enabled]
    Type: stdio
    Command: npx

# Add to Cursor only (not central registry)
$ damngood --client cursor add temp-server --command npx --args "-y package"
```

## Configuration Files

All configuration is stored in `~/.damngood/`:

- `registry.json` - Central MCP server registry
- `clients.json` - Registered AI tool clients

Config files for AI tools are managed by DamnGood and should not be edited manually when using central mode.

## Commands Reference

### Central Commands (Default)

| Command | Description |
|---------|-------------|
| `list` | List centrally managed servers |
| `add <name>` | Add server via JSON editor |
| `edit <name>` | Edit server via JSON editor |
| `remove <name>` | Remove from central registry |
| `show <name>` | Show server details |
| `sync` | Sync to all assigned clients |
| `import` | Import existing configs |

### Client Commands

| Command | Description |
|---------|-------------|
| `client list` | List registered clients |
| `client register <name>` | Register new client |
| `client remove <name>` | Remove registered client |
| `client enable <name>` | Enable client for sync |
| `client disable <name>` | Disable client |

### Single-Client Commands (with `--client`)

| Command | Description |
|---------|-------------|
| `list` | List client's servers |
| `add <name>` | Add to single client |
| `remove <name>` | Remove from single client |
| `enable/disable/toggle <name>` | Change server state |
| `export <path>` | Export client's config |

## Tips

- **Auto-discovery**: Run `damngood client list` after installing a new AI tool
- **Selective sync**: Use the `clients` array to control which tools get each server
- **Quick edits**: `damngood edit <name>` is faster than manual JSON editing
- **Migration**: Use `import` to gradually move from manual configs to central management

## Why Use This?

- **One source of truth** - Central registry eliminates config drift
- **DRY principle** - Define once, use everywhere
- **Safe editing** - JSON validation prevents syntax errors
- **Editor of choice** - Use your preferred editor for configs
- **Flexible** - Works with any MCP-compatible tool
- **Non-destructive** - Import preserves existing configs
