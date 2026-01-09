import { randomBytes, createHash } from 'crypto';
import { logger } from '../utils/logger.js';
import { startCallbackServer } from './callback-server.js';
import { OAuthTokens, saveServerAuth, loadServerAuth, isTokenExpired } from './token-store.js';

export interface OAuthConfig {
  authorizationEndpoint: string;
  tokenEndpoint: string;
  clientId: string;
  clientSecret?: string;
  scopes?: string[];
}

export interface OAuthDiscovery {
  authorization_endpoint: string;
  token_endpoint: string;
  scopes_supported?: string[];
}

function generateCodeVerifier(): string {
  return randomBytes(32).toString('base64url');
}

function generateCodeChallenge(verifier: string): string {
  return createHash('sha256').update(verifier).digest('base64url');
}

function generateState(): string {
  return randomBytes(16).toString('base64url');
}

export async function discoverOAuthEndpoints(serverUrl: string): Promise<OAuthDiscovery | null> {
  const url = new URL(serverUrl);
  const wellKnownUrl = `${url.origin}/.well-known/oauth-authorization-server`;

  try {
    const response = await fetch(wellKnownUrl);
    if (!response.ok) {
      logger.debug('OAuth discovery not available', { url: wellKnownUrl, status: response.status });
      return null;
    }
    const discovery = await response.json() as OAuthDiscovery;
    logger.info('Discovered OAuth endpoints', { discovery });
    return discovery;
  } catch (error) {
    logger.debug('OAuth discovery failed', { error });
    return null;
  }
}

export async function performOAuthFlow(
  serverUrl: string,
  config: OAuthConfig
): Promise<OAuthTokens> {
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = generateCodeChallenge(codeVerifier);
  const state = generateState();

  // Start callback server
  const { result: callbackPromise, port, close } = await startCallbackServer();

  const redirectUri = `http://127.0.0.1:${port}/oauth/callback`;

  // Build authorization URL
  const authUrl = new URL(config.authorizationEndpoint);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('client_id', config.clientId);
  authUrl.searchParams.set('redirect_uri', redirectUri);
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('code_challenge', codeChallenge);
  authUrl.searchParams.set('code_challenge_method', 'S256');

  if (config.scopes && config.scopes.length > 0) {
    authUrl.searchParams.set('scope', config.scopes.join(' '));
  }

  logger.info('Starting OAuth flow', { authUrl: authUrl.toString() });

  // Open browser
  const open = (await import('open')).default;
  await open(authUrl.toString());

  // Wait for callback
  let callbackResult;
  try {
    callbackResult = await callbackPromise;
  } catch (error) {
    close();
    throw error;
  }

  // Verify state
  if (callbackResult.state !== state) {
    throw new Error('OAuth state mismatch');
  }

  // Exchange code for tokens
  const tokenResponse = await fetch(config.tokenEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code: callbackResult.code,
      redirect_uri: redirectUri,
      client_id: config.clientId,
      code_verifier: codeVerifier,
      ...(config.clientSecret && { client_secret: config.clientSecret }),
    }),
  });

  if (!tokenResponse.ok) {
    const errorText = await tokenResponse.text();
    logger.error('Token exchange failed', { status: tokenResponse.status, error: errorText });
    throw new Error(`Token exchange failed: ${tokenResponse.status}`);
  }

  const tokenData = await tokenResponse.json() as {
    access_token: string;
    refresh_token?: string;
    expires_in?: number;
    token_type: string;
    scope?: string;
  };

  const tokens: OAuthTokens = {
    accessToken: tokenData.access_token,
    refreshToken: tokenData.refresh_token,
    expiresAt: tokenData.expires_in ? Date.now() + tokenData.expires_in * 1000 : undefined,
    tokenType: tokenData.token_type,
    scope: tokenData.scope,
  };

  // Save tokens
  saveServerAuth({
    serverUrl,
    tokens,
    clientId: config.clientId,
  });

  logger.info('OAuth flow completed successfully');
  return tokens;
}

export async function refreshAccessToken(
  serverUrl: string,
  config: OAuthConfig,
  refreshToken: string
): Promise<OAuthTokens> {
  const tokenResponse = await fetch(config.tokenEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
      client_id: config.clientId,
      ...(config.clientSecret && { client_secret: config.clientSecret }),
    }),
  });

  if (!tokenResponse.ok) {
    const errorText = await tokenResponse.text();
    logger.error('Token refresh failed', { status: tokenResponse.status, error: errorText });
    throw new Error(`Token refresh failed: ${tokenResponse.status}`);
  }

  const tokenData = await tokenResponse.json() as {
    access_token: string;
    refresh_token?: string;
    expires_in?: number;
    token_type: string;
    scope?: string;
  };

  const tokens: OAuthTokens = {
    accessToken: tokenData.access_token,
    refreshToken: tokenData.refresh_token || refreshToken,
    expiresAt: tokenData.expires_in ? Date.now() + tokenData.expires_in * 1000 : undefined,
    tokenType: tokenData.token_type,
    scope: tokenData.scope,
  };

  // Save updated tokens
  saveServerAuth({
    serverUrl,
    tokens,
    clientId: config.clientId,
  });

  logger.info('Token refreshed successfully');
  return tokens;
}

export async function getValidTokens(
  serverUrl: string,
  config: OAuthConfig
): Promise<OAuthTokens | null> {
  const auth = loadServerAuth(serverUrl);

  if (!auth?.tokens) {
    return null;
  }

  if (!isTokenExpired(auth.tokens)) {
    return auth.tokens;
  }

  // Try to refresh if we have a refresh token
  if (auth.tokens.refreshToken) {
    try {
      return await refreshAccessToken(serverUrl, config, auth.tokens.refreshToken);
    } catch (error) {
      logger.warn('Token refresh failed, need re-authentication', { error });
      return null;
    }
  }

  return null;
}
