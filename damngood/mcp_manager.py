"""
A tool to manage MCP (Model Context Protocol) servers across multiple AI assistants
"""
import json
import os
import platform as _platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

try:
    from damngood.tui import (
        console,
        print_logo,
        print_welcome,
        print_header,
        print_success,
        print_error,
        print_warning,
        print_info,
        print_server_list,
        print_server_detail,
        print_client_list,
        print_legacy_server_list,
        print_sync_header,
        print_sync_client,
        print_sync_complete,
        print_import_found,
        print_import_result,
        create_sync_progress,
    )
    HAS_TUI = True
except ImportError:
    HAS_TUI = False

# Platform Detection
def _detect_os() -> str:
    """Detect the current operating system."""
    system = _platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    return "linux"

CURRENT_OS = _detect_os()


def _get_appdata() -> Path:
    """Get the Windows %APPDATA% directory (or equivalent fallback)."""
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))


def _get_localappdata() -> Path:
    """Get the Windows %LOCALAPPDATA% directory (or equivalent fallback)."""
    return Path(
        os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    )


# Default Client Paths (platform-aware)

def _build_client_paths() -> Dict[str, Path]:
    """Build platform-specific default paths for MCP client configs."""
    home = Path.home()
    paths: Dict[str, Path] = {}

    # Cursor — same dotfile path on all platforms
    paths["cursor"] = home / ".cursor" / "mcp.json"

    # Gemini CLI — same dotfile path on all platforms
    paths["gemini"] = home / ".gemini" / "settings.json"

    # Claude Code (CLI) — stores MCP servers in ~/.claude.json on all platforms
    paths["claude"] = home / ".claude.json"

    # Claude Desktop — platform-specific application data
    if CURRENT_OS == "macos":
        paths["claude_desktop"] = (
            home / "Library" / "Application Support" / "Claude"
            / "claude_desktop_config.json"
        )
    elif CURRENT_OS == "windows":
        paths["claude_desktop"] = (
            _get_appdata() / "Claude" / "claude_desktop_config.json"
        )
    else:  # linux
        paths["claude_desktop"] = (
            home / ".config" / "Claude" / "claude_desktop_config.json"
        )

    # OpenCode — primary path is $HOME/.opencode.json everywhere
    paths["opencode"] = home / ".opencode.json"

    return paths


DEFAULT_CLIENT_PATHS = _build_client_paths()


# Config keys for different clients
CLIENT_CONFIG_KEYS = {
    "cursor": "mcpServers",
    "gemini": "mcpServers",
    "opencode": "mcpServers",
    "claude": "mcpServers",
    "claude_desktop": "mcpServers",
}

# DamnGood config directory
DAMNGOOD_DIR = Path.home() / ".damngood"
REGISTRY_FILE = DAMNGOOD_DIR / "registry.json"
CLIENTS_FILE = DAMNGOOD_DIR / "clients.json"


def get_editor() -> str:
    """Get the editor command from environment or fallback"""
    editor = os.environ.get("EDITOR")
    if editor:
        return editor

    # Platform-aware fallback chain
    if CURRENT_OS == "windows":
        candidates = ["code", "notepad++", "notepad"]
    else:
        candidates = ["nano", "vim", "vi"]

    for cmd in candidates:
        if shutil.which(cmd):
            return cmd

    raise RuntimeError("No editor found. Please set EDITOR environment variable.")


class ClientManager:
    """Manages AI tool clients (Cursor, Gemini, etc.)"""

    @classmethod
    def ensure_config_dir(cls):
        """Ensure the damngood config directory exists"""
        DAMNGOOD_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load_clients(cls) -> Dict[str, Dict[str, Any]]:
        """Load registered clients from config"""
        if CLIENTS_FILE.exists():
            with open(CLIENTS_FILE, "r") as f:
                data = json.load(f)
                return data.get("clients", {})
        return {}

    @classmethod
    def save_clients(cls, clients: Dict[str, Dict[str, Any]]):
        """Save registered clients to config"""
        cls.ensure_config_dir()
        with open(CLIENTS_FILE, "w") as f:
            json.dump({"clients": clients}, f, indent=2)

    @classmethod
    def discover_clients(cls) -> Dict[str, Dict[str, Any]]:
        """Auto-discover clients by checking if their config files exist"""
        discovered = {}
        for client_name, config_path in DEFAULT_CLIENT_PATHS.items():
            if config_path.exists():
                discovered[client_name] = {
                    "name": client_name,
                    "path": str(config_path),
                    "key": CLIENT_CONFIG_KEYS[client_name],
                    "auto_discovered": True,
                    "enabled": True,
                }
        return discovered

    @classmethod
    def init_clients(cls):
        """Initialize clients - merge discovered with existing"""
        existing = cls.load_clients()
        discovered = cls.discover_clients()

        # Merge: keep existing settings but add newly discovered clients
        for name, client in discovered.items():
            if name not in existing:
                existing[name] = client

        cls.save_clients(existing)
        return existing

    @classmethod
    def list_clients(cls):
        """List all clients with their status"""
        clients = cls.init_clients()

        if HAS_TUI:
            print_client_list(clients)
            return

        if not clients:
            print("No clients registered. Use 'damngood client register' to add one.")
            return

        print("\nRegistered Clients:")
        print("-" * 70)
        print(f"{'Name':<15} {'Status':<10} {'Auto':<6} {'Config Path'}")
        print("-" * 70)

        for name, client in sorted(clients.items()):
            status = "enabled" if client.get("enabled", True) else "disabled"
            auto = "yes" if client.get("auto_discovered", False) else "no"
            path = client.get("path", "N/A")
            print(f"{name:<15} {status:<10} {auto:<6} {path}")

        print()

    @classmethod
    def register_client(cls, name: str, path: str, key: str = "mcpServers"):
        """Register a new client"""
        clients = cls.load_clients()
        name = name.lower()

        clients[name] = {
            "name": name,
            "path": path,
            "key": key,
            "auto_discovered": False,
            "enabled": True,
        }

        cls.save_clients(clients)
        if HAS_TUI:
            print_success(f"Registered client [client.name]{name}[/client.name] → {path} (key: {key})")
        else:
            print(f"Registered client '{name}' -> {path} (key: {key})")

    @classmethod
    def remove_client(cls, name: str):
        """Remove a client (only if not auto-discovered)"""
        clients = cls.load_clients()
        name = name.lower()

        if name not in clients:
            if HAS_TUI:
                print_error(f"Client '{name}' not found")
            else:
                print(f"Client '{name}' not found")
            sys.exit(1)

        if clients[name].get("auto_discovered", False):
            if HAS_TUI:
                print_warning(f"Cannot remove auto-discovered client '{name}'. Use 'disable' instead.")
            else:
                print(
                    f"Cannot remove auto-discovered client '{name}'. Use 'disable' instead."
                )
            sys.exit(1)

        del clients[name]
        cls.save_clients(clients)
        if HAS_TUI:
            print_success(f"Removed client [client.name]{name}[/client.name]")
        else:
            print(f"Removed client '{name}'")

    @classmethod
    def set_enabled(cls, name: str, enabled: bool):
        """Enable or disable a client"""
        clients = cls.load_clients()
        name = name.lower()

        if name not in clients:
            print(f"Client '{name}' not found")
            sys.exit(1)

        clients[name]["enabled"] = enabled
        cls.save_clients(clients)
        status = "enabled" if enabled else "disabled"
        if HAS_TUI:
            print_success(f"Client [client.name]{name}[/client.name] {status}")
        else:
            print(f"Client '{name}' {status}")

    @classmethod
    def get_enabled_clients(cls) -> Dict[str, Dict[str, Any]]:
        """Get only enabled clients"""
        clients = cls.load_clients()
        return {k: v for k, v in clients.items() if v.get("enabled", True)}


class CentralRegistry:
    """Manages the central MCP server registry"""

    @classmethod
    def ensure_config_dir(cls):
        """Ensure the damngood config directory exists"""
        DAMNGOOD_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load_registry(cls) -> Dict[str, Any]:
        """Load the central registry"""
        if REGISTRY_FILE.exists():
            with open(REGISTRY_FILE, "r") as f:
                return json.load(f)
        return {"servers": {}}

    @classmethod
    def save_registry(cls, registry: Dict[str, Any]):
        """Save the central registry"""
        cls.ensure_config_dir()
        with open(REGISTRY_FILE, "w") as f:
            json.dump(registry, f, indent=2)

    @classmethod
    def list_servers(cls):
        """List all centrally managed servers"""
        registry = cls.load_registry()
        servers = registry.get("servers", {})

        if HAS_TUI:
            print_server_list(servers, title="Centrally Managed Servers")
            return

        if not servers:
            print(
                "No servers in central registry. Use 'damngood add <name>' to add one."
            )
            return

        print("\nCentrally Managed Servers:")
        print("-" * 70)
        print(f"{'Name':<20} {'Command':<30} {'Clients'}")
        print("-" * 70)

        for name, config in sorted(servers.items()):
            cmd = config.get("command", "N/A")
            args = " ".join(config.get("args", []))
            full_cmd = f"{cmd} {args}"[:28]
            clients = ", ".join(config.get("clients", []))
            print(f"{name:<20} {full_cmd:<30} {clients}")

        print()

    @classmethod
    def show_server(cls, name: str):
        """Show detailed information about a server"""
        registry = cls.load_registry()
        servers = registry.get("servers", {})

        if name not in servers:
            if HAS_TUI:
                print_error(f"Server '{name}' not found in central registry")
            else:
                print(f"Server '{name}' not found in central registry")
            sys.exit(1)

        config = servers[name]

        if HAS_TUI:
            print_server_detail(name, config)
            return

        print(f"\nServer: {name}")
        print("-" * 40)
        print(f"Type: {config.get('type', 'stdio')}")
        print(f"Command: {config.get('command', 'N/A')}")
        print(f"Args: {config.get('args', [])}")
        print(f"Env: {config.get('env', {})}")
        print(f"Clients: {', '.join(config.get('clients', []))}")
        if "created_at" in config:
            print(f"Created: {config['created_at']}")
        if "updated_at" in config:
            print(f"Updated: {config['updated_at']}")
        print()

    @classmethod
    def add_server(cls, name: str):
        """Add a server by opening editor with template"""
        registry = cls.load_registry()

        # Check if server already exists
        if name in registry.get("servers", {}):
            print(
                f"Server '{name}' already exists. Use 'damngood edit {name}' to modify."
            )
            sys.exit(1)

        # Create template
        template = {
            "type": "stdio",
            "command": "npx",
            "args": [],
            "env": {},
            "clients": [],
        }

        # Open editor
        editor = get_editor()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json.dumps(template, indent=2))
            temp_path = f.name

        try:
            subprocess.run([editor, temp_path], check=True)

            # Read and validate
            with open(temp_path, "r") as f:
                config = json.load(f)

            # Add timestamps
            now = datetime.now().isoformat()
            config["created_at"] = now
            config["updated_at"] = now

            # Save to registry
            if "servers" not in registry:
                registry["servers"] = {}
            registry["servers"][name] = config
            cls.save_registry(registry)

            if HAS_TUI:
                print_success(f"Added server [server.name]{name}[/server.name] to central registry")
            else:
                print(f"Added server '{name}' to central registry")

        except json.JSONDecodeError as e:
            if HAS_TUI:
                print_error(f"Invalid JSON - {e}")
            else:
                print(f"Error: Invalid JSON - {e}")
            sys.exit(1)
        except subprocess.CalledProcessError:
            if HAS_TUI:
                print_warning("Editor closed without saving. Server not added.")
            else:
                print("Editor closed without saving. Server not added.")
            sys.exit(1)
        finally:
            os.unlink(temp_path)

    @classmethod
    def edit_server(cls, name: str):
        """Edit a server by opening editor with current config"""
        registry = cls.load_registry()
        servers = registry.get("servers", {})

        if name not in servers:
            if HAS_TUI:
                print_error(f"Server '{name}' not found in central registry")
            else:
                print(f"Server '{name}' not found in central registry")
            sys.exit(1)

        config = servers[name]

        # Open editor
        editor = get_editor()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json.dumps(config, indent=2))
            temp_path = f.name

        try:
            subprocess.run([editor, temp_path], check=True)

            # Read and validate
            with open(temp_path, "r") as f:
                new_config = json.load(f)

            # Update timestamp
            new_config["updated_at"] = datetime.now().isoformat()
            # Preserve created_at
            if "created_at" in config:
                new_config["created_at"] = config["created_at"]

            # Save to registry
            registry["servers"][name] = new_config
            cls.save_registry(registry)

            if HAS_TUI:
                print_success(f"Updated server [server.name]{name}[/server.name] in central registry")
            else:
                print(f"Updated server '{name}' in central registry")

        except json.JSONDecodeError as e:
            if HAS_TUI:
                print_error(f"Invalid JSON - {e}")
            else:
                print(f"Error: Invalid JSON - {e}")
            sys.exit(1)
        except subprocess.CalledProcessError:
            if HAS_TUI:
                print_warning("Editor closed without saving. Changes discarded.")
            else:
                print("Editor closed without saving. Changes discarded.")
            sys.exit(1)
        finally:
            os.unlink(temp_path)

    @classmethod
    def remove_server(cls, name: str):
        """Remove a server from central registry"""
        registry = cls.load_registry()
        servers = registry.get("servers", {})

        if name not in servers:
            if HAS_TUI:
                print_error(f"Server '{name}' not found")
            else:
                print(f"Server '{name}' not found")
            sys.exit(1)

        del registry["servers"][name]
        cls.save_registry(registry)
        if HAS_TUI:
            print_success(f"Removed server [server.name]{name}[/server.name] from central registry")
        else:
            print(f"Removed server '{name}' from central registry")

    @classmethod
    def sync(cls):
        """Sync central registry to all enabled clients"""
        registry = cls.load_registry()
        clients = ClientManager.get_enabled_clients()
        servers = registry.get("servers", {})

        if not servers:
            if HAS_TUI:
                print_warning("No servers to sync")
            else:
                print("No servers to sync")
            return

        if not clients:
            if HAS_TUI:
                print_warning("No enabled clients to sync to")
            else:
                print("No enabled clients to sync to")
            return

        if HAS_TUI:
            print_sync_header(len(servers), len(clients))
        else:
            print(f"\nSyncing {len(servers)} server(s) to {len(clients)} client(s)...\n")

        for client_name, client_config in clients.items():
            if not HAS_TUI:
                print(f"Syncing to {client_name}...")

            client_path = Path(client_config["path"]).expanduser()
            client_key = client_config["key"]

            # Load existing client config or create new
            if client_path.exists():
                with open(client_path, "r") as f:
                    client_data = json.load(f)
            else:
                client_data = {}

            # Initialize the mcp key if not exists
            if client_key not in client_data:
                client_data[client_key] = {}

            # Sync servers that have this client in their clients list
            synced_count = 0
            for server_name, server_config in servers.items():
                if client_name in server_config.get("clients", []):
                    # Copy config but remove internal fields
                    sync_config = {
                        k: v
                        for k, v in server_config.items()
                        if k not in ["clients", "created_at", "updated_at"]
                    }
                    # Ensure enabled field exists
                    if "enabled" not in sync_config:
                        sync_config["enabled"] = True
                    client_data[client_key][server_name] = sync_config
                    synced_count += 1

            # Save client config
            client_path.parent.mkdir(parents=True, exist_ok=True)
            with open(client_path, "w") as f:
                json.dump(client_data, f, indent=2)

            if HAS_TUI:
                print_sync_client(client_name, synced_count, str(client_path))
            else:
                print(f"  Synced {synced_count} server(s) to {client_path}")

        if HAS_TUI:
            print_sync_complete()
        else:
            print("\nSync complete!")

    @classmethod
    def import_configs(cls):
        """Import existing client configs into central registry"""
        clients = ClientManager.get_enabled_clients()
        registry = cls.load_registry()

        imported = []

        for client_name, client_config in clients.items():
            client_path = Path(client_config["path"]).expanduser()
            client_key = client_config["key"]

            if not client_path.exists():
                continue

            with open(client_path, "r") as f:
                client_data = json.load(f)

            servers = client_data.get(client_key, {})

            for server_name, server_config in servers.items():
                # Skip if already in registry
                if server_name in registry.get("servers", {}):
                    continue

                if HAS_TUI:
                    print_import_found(server_name, client_name)
                else:
                    print(f"\nFound server '{server_name}' in {client_name}")
                response = input("Import? [y]es / [n]o / [s]kip all: ").lower()

                if response == "s":
                    print("Skipping all remaining servers")
                    cls.save_registry(registry)
                    return
                elif response == "y":
                    # Add to registry
                    if "servers" not in registry:
                        registry["servers"] = {}

                    now = datetime.now().isoformat()
                    server_config["clients"] = [client_name]
                    server_config["created_at"] = now
                    server_config["updated_at"] = now

                    registry["servers"][server_name] = server_config
                    imported.append(server_name)
                    if HAS_TUI:
                        print_success(f"Imported [server.name]{server_name}[/server.name]")
                    else:
                        print(f"  Imported '{server_name}'")

        cls.save_registry(registry)

        if HAS_TUI:
            print_import_result(imported)
        else:
            if imported:
                print(f"\nImported {len(imported)} server(s): {', '.join(imported)}")
                print("Run 'damngood sync' to push to all clients")
            else:
                print("\nNo new servers to import")


class MCPServerManager:
    """Legacy single-client manager (for --client mode)"""

    # Client types and their MCP config keys
    CLIENT_FORMATS = {
        "opencode": "mcpServers",
        "cursor": "mcpServers",
        "gemini": "mcpServers",
        "claude": "mcpServers",
        "claude_desktop": "mcpServers",
        "generic": "mcpServers",
    }

    # Default config paths for each client type (platform-aware)
    @staticmethod
    def _build_legacy_client_paths() -> Dict[str, Path]:
        home = Path.home()
        paths = {
            "cursor": home / ".cursor" / "mcp.json",
            "gemini": home / ".gemini" / "settings.json",
            "claude": home / ".claude.json",
            "opencode": home / ".opencode.json",
            "generic": home / ".mcp" / "config.json",
        }
        # Claude Desktop — platform-specific
        if CURRENT_OS == "macos":
            paths["claude_desktop"] = (
                home / "Library" / "Application Support" / "Claude"
                / "claude_desktop_config.json"
            )
        elif CURRENT_OS == "windows":
            paths["claude_desktop"] = (
                _get_appdata() / "Claude" / "claude_desktop_config.json"
            )
        else:
            paths["claude_desktop"] = (
                home / ".config" / "Claude" / "claude_desktop_config.json"
            )
        return paths

    CLIENT_PATHS = _build_legacy_client_paths.__func__()

    # Path to store custom tool registrations
    CUSTOM_TOOLS_PATH = Path.home() / ".config" / "damngood" / "custom_tools.json"

    @classmethod
    def load_custom_tools(cls) -> Dict[str, Dict[str, str]]:
        """Load custom tool registrations"""
        if cls.CUSTOM_TOOLS_PATH.exists():
            with open(cls.CUSTOM_TOOLS_PATH, "r") as f:
                return json.load(f)
        return {}

    @classmethod
    def save_custom_tools(cls, tools: Dict[str, Dict[str, str]]):
        """Save custom tool registrations"""
        cls.CUSTOM_TOOLS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(cls.CUSTOM_TOOLS_PATH, "w") as f:
            json.dump(tools, f, indent=2)

    @classmethod
    def register_custom_tool(
        cls, name: str, config_path: str, config_key: str = "mcpServers"
    ):
        """Register a custom tool"""
        tools = cls.load_custom_tools()
        tools[name.lower()] = {"path": config_path, "key": config_key}
        cls.save_custom_tools(tools)
        print(f"Registered custom tool '{name}' -> {config_path} (key: {config_key})")

    def __init__(
        self, config_path: Optional[str] = None, client_type: Optional[str] = None
    ):
        # Load custom tools
        custom_tools = self.load_custom_tools()

        # Priority: 1) explicit config_path, 2) explicit client_type, 3) auto-detect
        if config_path:
            # User specified exact path
            self.config_path = Path(config_path)
            self.client_type = self._detect_client_type()
        elif client_type:
            # User specified which client to use - ignore any existing configs
            self.client_type = client_type.lower()
            if self.client_type in custom_tools:
                # Use custom tool registration
                self.config_path = Path(custom_tools[self.client_type]["path"])
            else:
                self.config_path = self.CLIENT_PATHS.get(
                    self.client_type, self.CLIENT_PATHS["generic"]
                )
        else:
            # Auto-detect from existing configs
            self.config_path = self._find_config()
            self.client_type = self._detect_client_type()
        self.config = self._load_config()

    def _detect_client_type(self) -> str:
        """Detect which MCP client this config belongs to"""
        path_str = str(self.config_path).lower()
        if "opencode" in path_str:
            return "opencode"
        elif "cursor" in path_str:
            return "cursor"
        elif "gemini" in path_str:
            return "gemini"
        elif "claude_desktop_config" in path_str or "claude desktop" in path_str:
            return "claude_desktop"
        elif "claude" in path_str:
            return "claude"
        return "generic"

    def _get_mcp_key(self) -> str:
        """Get the MCP config key for the current client"""
        custom_tools = self.load_custom_tools()
        if self.client_type in custom_tools:
            return custom_tools[self.client_type]["key"]
        return self.CLIENT_FORMATS.get(self.client_type, "mcpServers")

    def _find_config(self) -> Path:
        """Find the MCP config file in standard locations"""
        for path in DEFAULT_CONFIG_PATHS:
            if path.exists():
                return path
        return DEFAULT_CONFIG_PATHS[0]

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if not self.config_path.exists():
            return {self._get_mcp_key(): {}}
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in {self.config_path}")
            sys.exit(1)

    def save(self):
        """Save configuration to file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)
        print(f"Config saved to {self.config_path} ({self.client_type} format)")

    def list_servers(self):
        """List all configured MCP servers"""
        mcp_key = self._get_mcp_key()
        servers = self.config.get(mcp_key, {})

        if HAS_TUI:
            print_legacy_server_list(servers, self.client_type)
            return

        if not servers:
            print("No MCP servers configured.")
            return

        print(f"\nConfigured MCP Servers ({self.client_type}):")
        print("-" * 60)
        for name, config in servers.items():
            status = "enabled" if config.get("enabled", True) else "disabled"
            print(f"  {name:<20} [{status}]")
            print(f"    Type: {config.get('type', 'stdio')}")
            print(f"    Command: {config.get('command', 'N/A')}")
            print()

    def add_server(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        server_type: str = "stdio",
    ):
        """Add a new MCP server"""
        mcp_key = self._get_mcp_key()
        if mcp_key not in self.config:
            self.config[mcp_key] = {}

        self.config[mcp_key][name] = {
            "type": server_type,
            "command": command,
            "args": args or [],
            "env": env or {},
            "enabled": True,
        }
        print(f"Added MCP server: {name}")

    def remove_server(self, name: str):
        """Remove an MCP server"""
        mcp_key = self._get_mcp_key()
        if name in self.config.get(mcp_key, {}):
            del self.config[mcp_key][name]
            print(f"Removed MCP server: {name}")
        else:
            print(f"Server not found: {name}")
            sys.exit(1)

    def toggle_server(self, name: str, enabled: Optional[bool] = None):
        """Enable or disable an MCP server"""
        mcp_key = self._get_mcp_key()
        servers = self.config.get(mcp_key, {})
        if name not in servers:
            print(f"Server not found: {name}")
            sys.exit(1)

        if enabled is None:
            enabled = not servers[name].get("enabled", True)

        servers[name]["enabled"] = enabled
        status = "enabled" if enabled else "disabled"
        print(f"Server '{name}' {status}")

    def get_server(self, name: str) -> Dict[str, Any]:
        """Get server configuration"""
        mcp_key = self._get_mcp_key()
        return self.config.get(mcp_key, {}).get(name, {})

    def export_config(self, output_path: str):
        """Export configuration to a new file"""
        output = Path(output_path)
        with open(output, "w") as f:
            json.dump(self.config, f, indent=2)
        print(f"Config exported to {output}")

# Default Config Paths (legacy auto-detect, platform-aware)

def _build_config_paths() -> List[Path]:
    """Build platform-aware list of config paths for legacy auto-detection."""
    home = Path.home()
    cwd = Path.cwd()
    paths: List[Path] = []

    # Cursor
    paths.append(home / ".cursor" / "mcp.json")           # global
    paths.append(cwd / ".cursor" / "mcp.json")            # project-level
    if CURRENT_OS == "macos":
        paths.append(
            home / "Library" / "Application Support" / "Cursor"
            / "cursor_desktop_config.json"
        )
    elif CURRENT_OS == "windows":
        paths.append(_get_appdata() / "Cursor" / "cursor_desktop_config.json")

    # Gemini CLI 
    paths.append(home / ".gemini" / "settings.json")       # global
    paths.append(cwd / ".gemini" / "settings.json")        # project-level

    # OpenCode 
    paths.append(home / ".opencode.json")                  # primary global
    if CURRENT_OS != "windows":
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
        paths.append(xdg / "opencode" / ".opencode.json") # XDG global
        paths.append(xdg / "opencode" / "opencode.json")  # XDG alt
    else:
        paths.append(_get_appdata() / "opencode" / "opencode.json")
    paths.append(cwd / "opencode.json")                    # project-level
    paths.append(cwd / ".opencode" / "opencode.json")      # project alt

    # Claude Code (CLI) 
    paths.append(home / ".claude.json")                    # MCP config (user scope)
    paths.append(cwd / ".mcp.json")                        # MCP config (project scope)

    # Claude Desktop 
    if CURRENT_OS == "macos":
        paths.append(
            home / "Library" / "Application Support" / "Claude"
            / "claude_desktop_config.json"
        )
    elif CURRENT_OS == "windows":
        paths.append(_get_appdata() / "Claude" / "claude_desktop_config.json")
    else:
        paths.append(home / ".config" / "Claude" / "claude_desktop_config.json")

    # Generic / XDG MCP 
    paths.append(home / ".mcp" / "config.json")
    if CURRENT_OS != "windows":
        paths.append(home / ".config" / "mcp" / "config.json")
    paths.append(cwd / "mcp_config.json")

    return paths


DEFAULT_CONFIG_PATHS = _build_config_paths()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Damn Good MCP Server Manager - Centralized Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Management Modes:
  Central Mode (default):    Manage servers centrally across all clients
  Client Mode (--client):    Manage a single client's servers

Commands:
  # Central Management (default)
  damngood list                    List centrally managed servers
  damngood add <name>              Add server via JSON editor
  damngood edit <name>             Edit server via JSON editor
  damngood remove <name>           Remove from central registry
  damngood show <name>             Show server details
  damngood sync                    Sync to all clients
  damngood import                  Import existing configs

  # Client Management
  damngood client list             List registered clients
  damngood client register <name>  Register new client
  damngood client remove <name>    Remove registered client
  damngood client enable <name>    Enable client
  damngood client disable <name>   Disable client

  # Single-Client Mode (use --client)
  damngood --client cursor list    List Cursor servers only
  damngood --client cursor add ... Add to Cursor only

Examples:
  # Add a server to central registry
  damngood add filesystem
  # (opens editor, fill JSON, save, close)

  # Sync to all clients
  damngood sync

  # Or manage single client
  damngood --client cursor list
        """,
    )
    parser.add_argument("--config", "-c", help="Path to config file (legacy)")

    # Load custom tools for choices
    custom_tools = MCPServerManager.load_custom_tools()
    client_choices = [
        "cursor", "gemini", "opencode", "claude", "claude_desktop", "generic",
    ] + list(custom_tools.keys())

    parser.add_argument(
        "--client",
        choices=client_choices,
        help="Manage single client only (skips central registry)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List MCP servers")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new MCP server")
    add_parser.add_argument("name", help="Server name")
    add_parser.add_argument(
        "--command", "-cmd", help="Command to run (legacy mode only)"
    )
    add_parser.add_argument(
        "--args", "-a", nargs="*", help="Arguments (legacy mode only)"
    )
    add_parser.add_argument(
        "--env",
        "-e",
        nargs="*",
        help="Environment variables (KEY=VALUE) (legacy mode only)",
    )
    add_parser.add_argument(
        "--type", default="stdio", help="Server type (legacy mode only)"
    )

    # Edit command
    edit_parser = subparsers.add_parser("edit", help="Edit an MCP server")
    edit_parser.add_argument("name", help="Server name")

    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove an MCP server")
    remove_parser.add_argument("name", help="Server name")

    # Show command
    show_parser = subparsers.add_parser("show", help="Show server details")
    show_parser.add_argument("name", help="Server name")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync to all clients")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import existing configs")

    # Enable/Disable commands (legacy)
    enable_parser = subparsers.add_parser("enable", help="Enable an MCP server")
    enable_parser.add_argument("name", help="Server name")

    disable_parser = subparsers.add_parser("disable", help="Disable an MCP server")
    disable_parser.add_argument("name", help="Server name")

    # Toggle command (legacy)
    toggle_parser = subparsers.add_parser("toggle", help="Toggle an MCP server")
    toggle_parser.add_argument("name", help="Server name")

    # Export command (legacy)
    export_parser = subparsers.add_parser("export", help="Export config to file")
    export_parser.add_argument("path", help="Output file path")

    # Register command for custom tools (legacy)
    register_parser = subparsers.add_parser(
        "register", help="Register a custom MCP client tool"
    )
    register_parser.add_argument("name", help="Tool name (e.g., 'mytool')")
    register_parser.add_argument(
        "--path", "-p", required=True, help="Path to config file"
    )
    register_parser.add_argument(
        "--key",
        "-k",
        default="mcpServers",
        help="Config key (default: mcpServers, use 'mcp' for OpenCode-style)",
    )

    # Client subcommand
    client_parser = subparsers.add_parser("client", help="Manage clients")
    client_subparsers = client_parser.add_subparsers(
        dest="client_command", help="Client commands"
    )

    # Client list
    client_list_parser = client_subparsers.add_parser(
        "list", help="List registered clients"
    )

    # Client register
    client_register_parser = client_subparsers.add_parser(
        "register", help="Register a client"
    )
    client_register_parser.add_argument("name", help="Client name")
    client_register_parser.add_argument(
        "--path", "-p", required=True, help="Config file path"
    )
    client_register_parser.add_argument(
        "--key", "-k", default="mcpServers", help="Config key"
    )

    # Client remove
    client_remove_parser = client_subparsers.add_parser(
        "remove", help="Remove a client"
    )
    client_remove_parser.add_argument("name", help="Client name")

    # Client enable/disable
    client_enable_parser = client_subparsers.add_parser(
        "enable", help="Enable a client"
    )
    client_enable_parser.add_argument("name", help="Client name")

    client_disable_parser = client_subparsers.add_parser(
        "disable", help="Disable a client"
    )
    client_disable_parser.add_argument("name", help="Client name")

    args = parser.parse_args()

    if not args.command:
        if HAS_TUI:
            print_welcome()
        else:
            parser.print_help()
        sys.exit(0)

    # Handle client subcommands
    if args.command == "client":
        if not args.client_command:
            client_parser.print_help()
            sys.exit(1)

        if args.client_command == "list":
            ClientManager.list_clients()
        elif args.client_command == "register":
            ClientManager.register_client(args.name, args.path, args.key)
        elif args.client_command == "remove":
            ClientManager.remove_client(args.name)
        elif args.client_command == "enable":
            ClientManager.set_enabled(args.name, True)
        elif args.client_command == "disable":
            ClientManager.set_enabled(args.name, False)
        return

    # Legacy single-client mode (--client flag or auto-detect)
    if args.client or (
        args.command in ["enable", "disable", "toggle", "export", "register"]
        and not args.command == "client"
    ):
        # Check if this is a central command or legacy command
        central_commands = ["sync", "import", "show", "edit"]

        if args.command in central_commands and not args.client:
            # Use central registry
            if args.command == "sync":
                CentralRegistry.sync()
            elif args.command == "import":
                CentralRegistry.import_configs()
            elif args.command == "show":
                CentralRegistry.show_server(args.name)
            elif args.command == "edit":
                CentralRegistry.edit_server(args.name)
        else:
            # Use legacy single-client mode
            manager = MCPServerManager(args.config, args.client)

            if args.command == "list":
                manager.list_servers()

            elif args.command == "add":
                if args.command:
                    # Legacy mode with --command flag
                    env_dict = {}
                    if args.env:
                        for env_var in args.env:
                            key, value = env_var.split("=", 1)
                            env_dict[key] = value
                    manager.add_server(
                        args.name, args.command, args.args, env_dict, args.type
                    )
                    manager.save()
                else:
                    # Central mode - should not reach here
                    print(
                        "Error: Use 'damngood add <name>' without --client for central mode"
                    )
                    sys.exit(1)

            elif args.command == "remove":
                manager.remove_server(args.name)
                manager.save()

            elif args.command == "enable":
                manager.toggle_server(args.name, True)
                manager.save()

            elif args.command == "disable":
                manager.toggle_server(args.name, False)
                manager.save()

            elif args.command == "toggle":
                manager.toggle_server(args.name)
                manager.save()

            elif args.command == "export":
                manager.export_config(args.path)

            elif args.command == "register":
                MCPServerManager.register_custom_tool(args.name, args.path, args.key)
    else:
        # Central mode (default)
        if args.command == "list":
            CentralRegistry.list_servers()
        elif args.command == "add":
            CentralRegistry.add_server(args.name)
        elif args.command == "edit":
            CentralRegistry.edit_server(args.name)
        elif args.command == "remove":
            CentralRegistry.remove_server(args.name)
        elif args.command == "show":
            CentralRegistry.show_server(args.name)
        elif args.command == "sync":
            CentralRegistry.sync()
        elif args.command == "import":
            CentralRegistry.import_configs()
        else:
            # Command not available in central mode
            print(
                f"Command '{args.command}' requires --client flag for single-client mode"
            )
            sys.exit(1)

if __name__ == "__main__":
    main()