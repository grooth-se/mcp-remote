import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { homedir } from 'os';
import { join } from 'path';

describe('config', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('should use default config directory', async () => {
    delete process.env.MCP_REMOTE_CONFIG_DIR;
    delete process.env.MCP_REMOTE_LOG_DIR;

    const { getConfig } = await import('../src/utils/config.js');
    const config = getConfig();

    expect(config.configDir).toBe(join(homedir(), '.mcp-auth'));
    expect(config.logDir).toBe(join(homedir(), '.mcp-auth', 'logs'));
  });

  it('should use custom config directory from env', async () => {
    process.env.MCP_REMOTE_CONFIG_DIR = '/custom/config';
    process.env.MCP_REMOTE_LOG_DIR = '/custom/logs';

    const { getConfig } = await import('../src/utils/config.js');
    const config = getConfig();

    expect(config.configDir).toBe('/custom/config');
    expect(config.logDir).toBe('/custom/logs');
  });

  it('should generate unique config paths for different servers', async () => {
    const { getServerConfigPath } = await import('../src/utils/config.js');

    const path1 = getServerConfigPath('https://server1.com/sse');
    const path2 = getServerConfigPath('https://server2.com/sse');

    expect(path1).not.toBe(path2);
    expect(path1).toContain('.json');
    expect(path2).toContain('.json');
  });
});
