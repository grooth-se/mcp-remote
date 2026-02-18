"""Application entry point."""

import os
from app import create_app

config_name = os.environ.get('FLASK_CONFIG') or 'default'
app = create_app(config_name)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
