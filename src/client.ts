import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';
import { logger } from './utils/logger.js';

export interface ClientOptions {
  serverUrl: string;
  headers?: Record<string, string>;
  allowHttp?: boolean;
}

export interface ConnectedClient {
  client: Client;
  transport: SSEClientTransport;
  close: () => Promise<void>;
}

export async function createSSEClient(options: ClientOptions): Promise<ConnectedClient> {
  const { serverUrl, headers = {}, allowHttp = false } = options;

  const url = new URL(serverUrl);

  if (url.protocol === 'http:' && !allowHttp) {
    throw new Error(
      'HTTP connections are not allowed by default. Use --allow-http to enable insecure connections.'
    );
  }

  logger.info('Creating SSE client', { serverUrl });

  const transport = new SSEClientTransport(new URL(serverUrl), {
    requestInit: {
      headers,
    },
  });

  const client = new Client(
    {
      name: 'mcp-remote',
      version: '1.0.0',
    },
    {
      capabilities: {},
    }
  );

  await client.connect(transport);
  logger.info('SSE client connected');

  return {
    client,
    transport,
    close: async () => {
      logger.info('Closing SSE client');
      await client.close();
    },
  };
}
