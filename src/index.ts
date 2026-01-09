#!/usr/bin/env node

import { program } from 'commander';
import { startProxy } from './proxy.js';
import {
  discoverOAuthEndpoints,
  performOAuthFlow,
  getValidTokens,
  OAuthConfig,
} from './auth/index.js';
import { logger } from './utils/logger.js';

interface CliOptions {
  header?: string[];
  allowHttp?: boolean;
}

function parseHeaders(headerArgs: string[] = []): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const header of headerArgs) {
    const colonIndex = header.indexOf(':');
    if (colonIndex === -1) {
      console.error(`Invalid header format: ${header}. Expected "Name: Value"`);
      process.exit(1);
    }
    const name = header.substring(0, colonIndex).trim();
    const value = header.substring(colonIndex + 1).trim();
    headers[name] = value;
  }
  return headers;
}

async function handleOAuth(serverUrl: string): Promise<string | null> {
  // Try to discover OAuth endpoints
  const discovery = await discoverOAuthEndpoints(serverUrl);

  if (!discovery) {
    logger.debug('No OAuth discovery available, proceeding without auth');
    return null;
  }

  // For now, use a default client ID - in production this would be configurable
  const config: OAuthConfig = {
    authorizationEndpoint: discovery.authorization_endpoint,
    tokenEndpoint: discovery.token_endpoint,
    clientId: 'mcp-remote',
    scopes: discovery.scopes_supported,
  };

  // Check for existing valid tokens
  const existingTokens = await getValidTokens(serverUrl, config);
  if (existingTokens) {
    logger.info('Using existing tokens');
    return `${existingTokens.tokenType} ${existingTokens.accessToken}`;
  }

  // Perform OAuth flow
  console.error('Authorization required. Opening browser...');
  const tokens = await performOAuthFlow(serverUrl, config);
  return `${tokens.tokenType} ${tokens.accessToken}`;
}

async function main() {
  program
    .name('mcp-remote')
    .description('Connect to a remote MCP server over SSE transport')
    .version('1.0.0')
    .argument('<server-url>', 'URL of the remote MCP server (e.g., https://example.com/sse)')
    .option('-H, --header <header...>', 'Add custom header (format: "Name: Value")')
    .option('--allow-http', 'Allow insecure HTTP connections (not recommended)')
    .action(async (serverUrl: string, options: CliOptions) => {
      try {
        const headers = parseHeaders(options.header);

        // Handle OAuth if no Authorization header provided
        if (!headers['Authorization'] && !headers['authorization']) {
          const authHeader = await handleOAuth(serverUrl);
          if (authHeader) {
            headers['Authorization'] = authHeader;
          }
        }

        logger.info('Starting mcp-remote', { serverUrl, allowHttp: options.allowHttp });

        await startProxy({
          serverUrl,
          headers,
          allowHttp: options.allowHttp,
        });
      } catch (error) {
        logger.error('Fatal error', { error });
        console.error('Error:', error instanceof Error ? error.message : error);
        process.exit(1);
      }
    });

  await program.parseAsync();
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
