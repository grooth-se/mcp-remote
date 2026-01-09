# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

mcp-remote is a local proxy that connects MCP clients to remote MCP servers over SSE (Server-Sent Events) transport. It handles authentication flows including OAuth and acts as a stdio-to-SSE bridge.

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
# Basic usage - connect to a remote MCP server
npx mcp-remote https://remote.mcp.server/sse

# With custom headers
npx mcp-remote https://remote.mcp.server/sse --header "Authorization: Bearer <token>"

# Allow HTTP (non-HTTPS) connections
npx mcp-remote http://localhost:8080/sse --allow-http
```

## Environment Variables

- `MCP_REMOTE_CONFIG_DIR` - Override config/auth storage location (default: `~/.mcp-auth`)
- `MCP_REMOTE_LOG_DIR` - Override log file location

## Architecture

```
src/
├── index.ts          # CLI entry point (commander-based)
├── proxy.ts          # stdio <-> SSE bridge using MCP SDK
├── client.ts         # SSE client wrapper
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
2. mcp-remote establishes SSE connection to remote server
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
      "args": ["mcp-remote", "https://remote.mcp.server/sse"]
    }
  }
}
```
