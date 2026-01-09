import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

// Mock the config before importing token-store
vi.mock('../src/utils/config.js', () => {
  const testDir = mkdtempSync(join(tmpdir(), 'mcp-remote-test-'));
  return {
    getConfig: () => ({
      configDir: testDir,
      logDir: join(testDir, 'logs'),
    }),
    getServerConfigPath: (serverUrl: string) => {
      const urlHash = Buffer.from(serverUrl).toString('base64url');
      return join(testDir, `${urlHash}.json`);
    },
  };
});

// Mock logger to avoid file operations
vi.mock('../src/utils/logger.js', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

import {
  loadServerAuth,
  saveServerAuth,
  isTokenExpired,
  OAuthTokens,
  ServerAuth,
} from '../src/auth/token-store.js';
import { getConfig } from '../src/utils/config.js';

describe('token-store', () => {
  let testDir: string;

  beforeEach(() => {
    testDir = getConfig().configDir;
  });

  afterEach(() => {
    if (existsSync(testDir)) {
      rmSync(testDir, { recursive: true, force: true });
    }
  });

  describe('saveServerAuth and loadServerAuth', () => {
    it('should save and load server auth', () => {
      const auth: ServerAuth = {
        serverUrl: 'https://example.com/sse',
        tokens: {
          accessToken: 'test-access-token',
          refreshToken: 'test-refresh-token',
          expiresAt: Date.now() + 3600000,
          tokenType: 'Bearer',
          scope: 'read write',
        },
        clientId: 'test-client',
      };

      saveServerAuth(auth);
      const loaded = loadServerAuth('https://example.com/sse');

      expect(loaded).toEqual(auth);
    });

    it('should return null for non-existent server', () => {
      const loaded = loadServerAuth('https://nonexistent.com/sse');
      expect(loaded).toBeNull();
    });

    it('should handle different server URLs separately', () => {
      const auth1: ServerAuth = {
        serverUrl: 'https://server1.com/sse',
        tokens: {
          accessToken: 'token1',
          tokenType: 'Bearer',
        },
      };

      const auth2: ServerAuth = {
        serverUrl: 'https://server2.com/sse',
        tokens: {
          accessToken: 'token2',
          tokenType: 'Bearer',
        },
      };

      saveServerAuth(auth1);
      saveServerAuth(auth2);

      const loaded1 = loadServerAuth('https://server1.com/sse');
      const loaded2 = loadServerAuth('https://server2.com/sse');

      expect(loaded1?.tokens?.accessToken).toBe('token1');
      expect(loaded2?.tokens?.accessToken).toBe('token2');
    });
  });

  describe('isTokenExpired', () => {
    it('should return false for tokens without expiry', () => {
      const tokens: OAuthTokens = {
        accessToken: 'test',
        tokenType: 'Bearer',
      };
      expect(isTokenExpired(tokens)).toBe(false);
    });

    it('should return false for non-expired tokens', () => {
      const tokens: OAuthTokens = {
        accessToken: 'test',
        tokenType: 'Bearer',
        expiresAt: Date.now() + 3600000, // 1 hour from now
      };
      expect(isTokenExpired(tokens)).toBe(false);
    });

    it('should return true for expired tokens', () => {
      const tokens: OAuthTokens = {
        accessToken: 'test',
        tokenType: 'Bearer',
        expiresAt: Date.now() - 1000, // 1 second ago
      };
      expect(isTokenExpired(tokens)).toBe(true);
    });

    it('should return true for tokens expiring within 5 minutes', () => {
      const tokens: OAuthTokens = {
        accessToken: 'test',
        tokenType: 'Bearer',
        expiresAt: Date.now() + 60000, // 1 minute from now
      };
      expect(isTokenExpired(tokens)).toBe(true);
    });
  });
});
