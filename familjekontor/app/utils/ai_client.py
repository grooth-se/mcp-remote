"""Ollama AI client wrapper with graceful degradation.

All functions return None or sensible defaults when Ollama is unavailable.
"""

import json
import logging
from flask import current_app

logger = logging.getLogger(__name__)


def is_ollama_available():
    """Check if Ollama is running and accessible."""
    if not current_app.config.get('OLLAMA_ENABLED'):
        return False

    try:
        import urllib.request
        host = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')
        req = urllib.request.Request(f'{host}/api/tags', method='GET')
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_available_models():
    """List models available in Ollama."""
    if not current_app.config.get('OLLAMA_ENABLED'):
        return []

    try:
        import urllib.request
        host = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')
        req = urllib.request.Request(f'{host}/api/tags', method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return [m['name'] for m in data.get('models', [])]
    except Exception:
        return []


def generate_text(prompt, system_prompt=None, temperature=0.3):
    """Generate text using Ollama.

    Returns the generated text string, or None if unavailable.
    """
    if not current_app.config.get('OLLAMA_ENABLED'):
        return None

    try:
        import urllib.request
        host = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')
        model = current_app.config.get('OLLAMA_MODEL', 'llama3.2')
        timeout = current_app.config.get('OLLAMA_TIMEOUT', 30)

        payload = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {'temperature': temperature},
        }
        if system_prompt:
            payload['system'] = system_prompt

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f'{host}/api/generate',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
            return result.get('response', '').strip()

    except Exception as e:
        logger.warning('Ollama generate_text failed: %s', e)
        return None


def generate_structured(prompt, system_prompt=None, temperature=0.1):
    """Generate structured JSON output from Ollama.

    Returns a parsed dict/list, or None if unavailable or parse fails.
    """
    json_system = (system_prompt or '') + '\nDu MÅSTE svara med giltig JSON. Inget annat.'

    text = generate_text(prompt, system_prompt=json_system, temperature=temperature)
    if not text:
        return None

    # Try to extract JSON from response
    try:
        # Handle markdown code blocks
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            text = text.split('```')[1].split('```')[0]

        return json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        logger.warning('Failed to parse JSON from Ollama response: %s', text[:200])
        return None


def get_ollama_status():
    """Get a status dict for the admin page."""
    enabled = current_app.config.get('OLLAMA_ENABLED', False)
    host = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')
    model = current_app.config.get('OLLAMA_MODEL', 'llama3.2')

    status = {
        'enabled': enabled,
        'host': host,
        'model': model,
        'available': False,
        'models': [],
    }

    if enabled:
        status['available'] = is_ollama_available()
        if status['available']:
            status['models'] = get_available_models()

    return status
