import { createServer, IncomingMessage, ServerResponse, Server } from 'http';
import { URL } from 'url';
import { logger } from '../utils/logger.js';

export interface CallbackResult {
  code: string;
  state?: string;
}

export interface CallbackServerOptions {
  port?: number;
  timeout?: number;
}

const HTML_SUCCESS = `
<!DOCTYPE html>
<html>
<head>
  <title>Authorization Successful</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
    .container { text-align: center; padding: 2rem; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    h1 { color: #22c55e; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Authorization Successful</h1>
    <p>You can close this window and return to your terminal.</p>
  </div>
</body>
</html>
`;

const HTML_ERROR = `
<!DOCTYPE html>
<html>
<head>
  <title>Authorization Failed</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
    .container { text-align: center; padding: 2rem; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    h1 { color: #ef4444; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Authorization Failed</h1>
    <p>Please try again or check the terminal for more information.</p>
  </div>
</body>
</html>
`;

export function startCallbackServer(
  options: CallbackServerOptions = {}
): Promise<{ result: Promise<CallbackResult>; port: number; close: () => void }> {
  const { port = 0, timeout = 300000 } = options; // Default 5 min timeout

  return new Promise((resolveServer, rejectServer) => {
    let resultResolve: (result: CallbackResult) => void;
    let resultReject: (error: Error) => void;
    let timeoutId: NodeJS.Timeout;

    const resultPromise = new Promise<CallbackResult>((resolve, reject) => {
      resultResolve = resolve;
      resultReject = reject;
    });

    const server: Server = createServer((req: IncomingMessage, res: ServerResponse) => {
      if (!req.url) {
        res.writeHead(400);
        res.end('Bad Request');
        return;
      }

      const url = new URL(req.url, `http://localhost`);

      if (url.pathname === '/oauth/callback') {
        const code = url.searchParams.get('code');
        const state = url.searchParams.get('state');
        const error = url.searchParams.get('error');
        const errorDescription = url.searchParams.get('error_description');

        if (error) {
          logger.error('OAuth callback error', { error, errorDescription });
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end(HTML_ERROR);
          resultReject(new Error(`OAuth error: ${error} - ${errorDescription || 'Unknown error'}`));
          return;
        }

        if (!code) {
          logger.error('OAuth callback missing code');
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end(HTML_ERROR);
          resultReject(new Error('No authorization code received'));
          return;
        }

        logger.info('OAuth callback received code');
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(HTML_SUCCESS);
        resultResolve({ code, state: state || undefined });
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    });

    server.on('error', (error) => {
      logger.error('Callback server error', { error });
      rejectServer(error);
    });

    server.listen(port, '127.0.0.1', () => {
      const address = server.address();
      const actualPort = typeof address === 'object' && address ? address.port : port;

      logger.info('Callback server started', { port: actualPort });

      timeoutId = setTimeout(() => {
        resultReject(new Error('OAuth callback timeout'));
        server.close();
      }, timeout);

      const close = () => {
        clearTimeout(timeoutId);
        server.close();
      };

      // Close server when result is received
      resultPromise.finally(() => {
        setTimeout(close, 1000); // Give browser time to receive response
      });

      resolveServer({
        result: resultPromise,
        port: actualPort,
        close,
      });
    });
  });
}
