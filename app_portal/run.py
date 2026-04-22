"""Run the portal locally for development."""
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Port 5050 to avoid macOS AirPlay on 5000
    app.run(host='0.0.0.0', port=5050, debug=True)
