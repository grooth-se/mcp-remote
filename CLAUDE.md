# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

mcp-remote is a local proxy that connects MCP clients to remote MCP servers. It supports both Streamable HTTP (default) and SSE transports, handles OAuth authentication, and acts as a stdio-to-remote bridge.

## Build Commands

```bash
npm install          # Install dependencies
npm run build        # Compile TypeScript to dist/
npm run dev          # Watch mode for development
npm test             # Run tests with Vitest
npm run test:watch   # Run tests in watch mode
npm run lint         # Type-check without emitting
```

## Usage Commands

```bash
# Basic usage - connect using Streamable HTTP (default)
npx @grooth-se/mcp-remote https://remote.mcp.server/mcp

# Use SSE transport (legacy)
npx @grooth-se/mcp-remote https://remote.mcp.server/sse --transport sse

# With custom headers
npx @grooth-se/mcp-remote https://remote.mcp.server/mcp --header "Authorization: Bearer <token>"

# Allow HTTP (non-HTTPS) connections
npx @grooth-se/mcp-remote http://localhost:8080/mcp --allow-http
```

## Transport Types

- **http** (default): Streamable HTTP transport - uses POST requests with optional SSE streaming
- **sse**: Legacy Server-Sent Events transport - uses GET for SSE stream + POST for messages

## Environment Variables

- `MCP_REMOTE_CONFIG_DIR` - Override config/auth storage location (default: `~/.mcp-auth`)
- `MCP_REMOTE_LOG_DIR` - Override log file location

## Architecture

```
src/
├── index.ts          # CLI entry point (commander-based)
├── proxy.ts          # stdio <-> remote bridge using MCP SDK
├── client.ts         # Client wrapper (unused, SDK transports used directly)
├── auth/
│   ├── oauth.ts          # OAuth 2.0 PKCE flow
│   ├── callback-server.ts # Localhost HTTP server for OAuth callback
│   └── token-store.ts    # Persistent token storage (~/.mcp-auth)
└── utils/
    ├── config.ts     # Environment variable handling
    └── logger.ts     # File-based logging
```

### Message Flow

1. MCP client connects via stdio to mcp-remote
2. mcp-remote establishes connection to remote server (HTTP or SSE)
3. Request handlers in `proxy.ts` forward all MCP operations (tools, resources, prompts)
4. Responses are proxied back through stdio

### OAuth Flow

1. Discovers endpoints via `/.well-known/oauth-authorization-server`
2. Opens browser with PKCE challenge
3. Callback server receives authorization code at `/oauth/callback`
4. Exchanges code for tokens and stores in `~/.mcp-auth/`
5. Subsequent connections reuse stored tokens (auto-refresh when expired)

## Claude Desktop Integration

Configure in `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "remote-server": {
      "command": "npx",
      "args": ["@grooth-se/mcp-remote", "https://remote.mcp.server/mcp"]
    }
  }
}
```

For SSE transport:
```json
{
  "mcpServers": {
    "remote-server": {
      "command": "npx",
      "args": ["@grooth-se/mcp-remote", "https://remote.mcp.server/sse", "--transport", "sse"]
    }
  }
}
```
