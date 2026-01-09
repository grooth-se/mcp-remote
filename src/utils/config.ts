import { homedir } from 'os';
import { join } from 'path';

export interface Config {
  configDir: string;
  logDir: string;
}

export function getConfig(): Config {
  const defaultConfigDir = join(homedir(), '.mcp-auth');
  const defaultLogDir = join(homedir(), '.mcp-auth', 'logs');

  return {
    configDir: process.env.MCP_REMOTE_CONFIG_DIR || defaultConfigDir,
    logDir: process.env.MCP_REMOTE_LOG_DIR || defaultLogDir,
  };
}

export function getServerConfigPath(serverUrl: string): string {
  const config = getConfig();
  const urlHash = Buffer.from(serverUrl).toString('base64url');
  return join(config.configDir, `${urlHash}.json`);
}
