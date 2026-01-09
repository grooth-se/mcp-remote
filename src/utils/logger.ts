import { appendFileSync, mkdirSync, existsSync } from 'fs';
import { join } from 'path';
import { getConfig } from './config.js';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

let logFile: string | null = null;

function ensureLogDir(): void {
  const { logDir } = getConfig();
  if (!existsSync(logDir)) {
    mkdirSync(logDir, { recursive: true });
  }
  if (!logFile) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    logFile = join(logDir, `mcp-remote-${timestamp}.log`);
  }
}

function formatMessage(level: LogLevel, message: string, data?: unknown): string {
  const timestamp = new Date().toISOString();
  const dataStr = data ? ` ${JSON.stringify(data)}` : '';
  return `[${timestamp}] [${level.toUpperCase()}] ${message}${dataStr}\n`;
}

function writeLog(level: LogLevel, message: string, data?: unknown): void {
  try {
    ensureLogDir();
    if (logFile) {
      appendFileSync(logFile, formatMessage(level, message, data));
    }
  } catch {
    // Silently ignore logging errors to not disrupt stdio communication
  }
}

export const logger = {
  debug: (message: string, data?: unknown) => writeLog('debug', message, data),
  info: (message: string, data?: unknown) => writeLog('info', message, data),
  warn: (message: string, data?: unknown) => writeLog('warn', message, data),
  error: (message: string, data?: unknown) => writeLog('error', message, data),
};
