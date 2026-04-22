"""Ollama LLM client for local inference.

Configured for CPU-only operation with smaller models (Llama 3.1 8B, Mistral 7B).
"""
import json
import urllib.request
import urllib.error
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def _get_ollama_url():
    return current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')


def _get_model():
    return current_app.config.get('LLM_MODEL', 'llama3.1:8b')


def check_ollama_status():
    """Check if Ollama is running and return available models."""
    try:
        url = f'{_get_ollama_url()}/api/tags'
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            models = [m['name'] for m in data.get('models', [])]
            return {'online': True, 'models': models}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.warning(f'Ollama not available: {e}')
        return {'online': False, 'models': []}


def generate(prompt, model=None, temperature=None, max_tokens=None, system=None):
    """Generate text using Ollama with streaming.

    Uses streaming to avoid HTTP timeout on slow CPU inference.
    Each token keeps the connection alive, so generation can take
    as long as needed without timing out.

    Returns the generated text or None if unavailable.
    """
    model = model or _get_model()
    temperature = temperature if temperature is not None else current_app.config.get('LLM_TEMPERATURE', 0.3)
    max_tokens = max_tokens or current_app.config.get('LLM_MAX_TOKENS', 4096)

    payload = {
        'model': model,
        'prompt': prompt,
        'stream': True,
        'options': {
            'temperature': temperature,
            'num_predict': max_tokens,
        }
    }
    if system:
        payload['system'] = system

    try:
        url = f'{_get_ollama_url()}/api/generate'
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        # Long initial timeout — on CPU, prompt evaluation can take
        # several minutes before the first token is emitted.
        # Once streaming starts, each token arrives within seconds.
        with urllib.request.urlopen(req, timeout=900) as resp:
            chunks = []
            for line in resp:
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                try:
                    token_data = json.loads(line)
                    token = token_data.get('response', '')
                    if token:
                        chunks.append(token)
                    if token_data.get('done'):
                        break
                except json.JSONDecodeError:
                    continue
            result = ''.join(chunks)
            if result:
                logger.info(f'Ollama generated {len(result)} chars')
            return result if result else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.error(f'Ollama generate failed: {e}')
        return None


def generate_json(prompt, model=None, system=None):
    """Generate structured JSON output from Ollama."""
    model = model or _get_model()

    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'format': 'json',
        'options': {
            'temperature': 0.1,
            'num_predict': current_app.config.get('LLM_MAX_TOKENS', 4096),
        }
    }
    if system:
        payload['system'] = system

    try:
        url = f'{_get_ollama_url()}/api/generate'
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            text = result.get('response', '')
            return json.loads(text)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
        logger.error(f'Ollama JSON generate failed: {e}')
        return None


def get_embeddings(text, model=None):
    """Generate embeddings for a single text using Ollama."""
    model = model or current_app.config.get('EMBEDDING_MODEL', 'nomic-embed-text')

    payload = {
        'model': model,
        'input': text,
    }

    try:
        url = f'{_get_ollama_url()}/api/embed'
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('embeddings', [None])[0]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.error(f'Ollama embedding failed: {e}')
        return None


def get_embeddings_batch(texts, model=None, batch_size=20):
    """Generate embeddings for multiple texts using Ollama batch API.

    Sends texts in batches to avoid overwhelming the server.
    Returns list of embeddings (None for failed items).
    """
    model = model or current_app.config.get('EMBEDDING_MODEL', 'nomic-embed-text')
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        payload = {
            'model': model,
            'input': batch,
        }

        try:
            url = f'{_get_ollama_url()}/api/embed'
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                batch_embeddings = result.get('embeddings', [])
                all_embeddings.extend(batch_embeddings)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            logger.error(f'Ollama batch embedding failed for batch {i//batch_size}: {e}')
            all_embeddings.extend([None] * len(batch))

    return all_embeddings
