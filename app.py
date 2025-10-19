import os
from flask import Flask, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'test-secret-key')

@app.route('/')
def index():
    return "<h1>VCard App is Running!</h1><a href='/health'>Health Check</a>"

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
