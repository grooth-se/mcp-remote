import { describe, it, expect, vi } from 'vitest';

// Mock logger
vi.mock('../src/utils/logger.js', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

import { startCallbackServer } from '../src/auth/callback-server.js';

describe('callback-server', () => {
  it('should start server and return port', async () => {
    const { port, close, result } = await startCallbackServer({ port: 0 });

    expect(port).toBeGreaterThan(0);
    expect(typeof close).toBe('function');
    expect(result).toBeInstanceOf(Promise);

    // Attach a catch handler to prevent unhandled rejection when server closes
    result.catch(() => {});
    close();
  });

  it('should handle OAuth callback with code', async () => {
    const { port, close, result } = await startCallbackServer({ port: 0 });

    // Make callback request
    const callbackUrl = `http://127.0.0.1:${port}/oauth/callback?code=test-code&state=test-state`;

    fetch(callbackUrl).catch(() => {
      // Ignore fetch errors, we just need to trigger the callback
    });

    const callbackResult = await result;

    expect(callbackResult.code).toBe('test-code');
    expect(callbackResult.state).toBe('test-state');

    close();
  });

  it('should return 404 for unknown paths', async () => {
    const { port, close, result } = await startCallbackServer({ port: 0 });

    const response = await fetch(`http://127.0.0.1:${port}/unknown`);
    expect(response.status).toBe(404);

    result.catch(() => {});
    close();
  });
});
