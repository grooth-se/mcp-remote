import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { Transport } from '@modelcontextprotocol/sdk/shared/transport.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
  ListPromptsRequestSchema,
  GetPromptRequestSchema,
  ListResourceTemplatesRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { logger } from './utils/logger.js';

export type TransportType = 'sse' | 'http';

export interface ProxyOptions {
  serverUrl: string;
  headers?: Record<string, string>;
  allowHttp?: boolean;
  transport?: TransportType;
}

function createTransport(
  serverUrl: string,
  headers: Record<string, string>,
  transportType: TransportType
): Transport {
  const url = new URL(serverUrl);

  if (transportType === 'http') {
    logger.info('Using Streamable HTTP transport');
    return new StreamableHTTPClientTransport(url, {
      requestInit: {
        headers,
      },
    });
  } else {
    logger.info('Using SSE transport');
    return new SSEClientTransport(url, {
      requestInit: {
        headers,
      },
    });
  }
}

export async function startProxy(options: ProxyOptions): Promise<void> {
  const { serverUrl, headers = {}, allowHttp = false, transport = 'http' } = options;

  const url = new URL(serverUrl);

  if (url.protocol === 'http:' && !allowHttp) {
    throw new Error(
      'HTTP connections are not allowed by default. Use --allow-http to enable insecure connections.'
    );
  }

  logger.info('Starting proxy', { serverUrl, transport });

  // Create transport to remote server
  const remoteTransport = createTransport(serverUrl, headers, transport);

  // Create client to connect to remote server
  const remoteClient = new Client(
    {
      name: 'mcp-remote-proxy',
      version: '1.1.0',
    },
    {
      capabilities: {},
    }
  );

  // Connect to remote server
  await remoteClient.connect(remoteTransport);
  logger.info('Connected to remote server');

  // Create local server for stdio
  const localServer = new Server(
    {
      name: 'mcp-remote',
      version: '1.1.0',
    },
    {
      capabilities: {
        tools: {},
        resources: {},
        prompts: {},
      },
    }
  );

  // Proxy tool requests
  localServer.setRequestHandler(ListToolsRequestSchema, async () => {
    logger.debug('Proxying listTools request');
    const result = await remoteClient.listTools();
    return { tools: result.tools };
  });

  localServer.setRequestHandler(CallToolRequestSchema, async (request) => {
    logger.debug('Proxying callTool request', { tool: request.params.name });
    const result = await remoteClient.callTool({
      name: request.params.name,
      arguments: request.params.arguments,
    });
    return result;
  });

  // Proxy resource requests
  localServer.setRequestHandler(ListResourcesRequestSchema, async () => {
    logger.debug('Proxying listResources request');
    const result = await remoteClient.listResources();
    return { resources: result.resources };
  });

  localServer.setRequestHandler(ListResourceTemplatesRequestSchema, async () => {
    logger.debug('Proxying listResourceTemplates request');
    const result = await remoteClient.listResourceTemplates();
    return { resourceTemplates: result.resourceTemplates };
  });

  localServer.setRequestHandler(ReadResourceRequestSchema, async (request) => {
    logger.debug('Proxying readResource request', { uri: request.params.uri });
    const result = await remoteClient.readResource({ uri: request.params.uri });
    return { contents: result.contents };
  });

  // Proxy prompt requests
  localServer.setRequestHandler(ListPromptsRequestSchema, async () => {
    logger.debug('Proxying listPrompts request');
    const result = await remoteClient.listPrompts();
    return { prompts: result.prompts };
  });

  localServer.setRequestHandler(GetPromptRequestSchema, async (request) => {
    logger.debug('Proxying getPrompt request', { name: request.params.name });
    const result = await remoteClient.getPrompt({
      name: request.params.name,
      arguments: request.params.arguments,
    });
    return result;
  });

  // Create stdio transport
  const stdioTransport = new StdioServerTransport();

  // Handle shutdown
  const shutdown = async () => {
    logger.info('Shutting down proxy');
    await localServer.close();
    await remoteClient.close();
    process.exit(0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  // Connect local server to stdio
  await localServer.connect(stdioTransport);
  logger.info('Proxy running - stdio connected');

  // Keep process alive
  await new Promise(() => {});
}
