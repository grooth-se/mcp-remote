import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { dirname } from 'path';
import { getServerConfigPath, getConfig } from '../utils/config.js';
import { logger } from '../utils/logger.js';

export interface OAuthTokens {
  accessToken: string;
  refreshToken?: string;
  expiresAt?: number;
  tokenType: string;
  scope?: string;
}

export interface ServerAuth {
  serverUrl: string;
  tokens?: OAuthTokens;
  clientId?: string;
  clientSecret?: string;
}

function ensureConfigDir(): void {
  const { configDir } = getConfig();
  if (!existsSync(configDir)) {
    mkdirSync(configDir, { recursive: true });
  }
}

export function loadServerAuth(serverUrl: string): ServerAuth | null {
  const configPath = getServerConfigPath(serverUrl);

  try {
    if (!existsSync(configPath)) {
      return null;
    }
    const data = readFileSync(configPath, 'utf-8');
    const auth = JSON.parse(data) as ServerAuth;
    logger.debug('Loaded auth for server', { serverUrl });
    return auth;
  } catch (error) {
    logger.error('Failed to load server auth', { serverUrl, error });
    return null;
  }
}

export function saveServerAuth(auth: ServerAuth): void {
  ensureConfigDir();
  const configPath = getServerConfigPath(auth.serverUrl);

  try {
    const dir = dirname(configPath);
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
    writeFileSync(configPath, JSON.stringify(auth, null, 2));
    logger.info('Saved auth for server', { serverUrl: auth.serverUrl });
  } catch (error) {
    logger.error('Failed to save server auth', { serverUrl: auth.serverUrl, error });
    throw error;
  }
}

export function isTokenExpired(tokens: OAuthTokens): boolean {
  if (!tokens.expiresAt) {
    return false;
  }
  // Consider expired if less than 5 minutes remaining
  const bufferMs = 5 * 60 * 1000;
  return Date.now() + bufferMs >= tokens.expiresAt;
}

export function clearServerAuth(serverUrl: string): void {
  const configPath = getServerConfigPath(serverUrl);

  try {
    if (existsSync(configPath)) {
      const { unlinkSync } = require('fs');
      unlinkSync(configPath);
      logger.info('Cleared auth for server', { serverUrl });
    }
  } catch (error) {
    logger.error('Failed to clear server auth', { serverUrl, error });
  }
}
