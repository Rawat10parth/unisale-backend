from app import app as flask_app
import os
import json
import tempfile
from flask import jsonify

# Create temporary credentials file from environment variable
if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
    service_account_info = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
    
    # Create a temporary file for the credentials
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    with open(path, 'w') as f:
        json.dump(service_account_info, f)
    
    # Set environment variable to the path of the temp file
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = path

# Add a test route directly here for debugging
@flask_app.route('/api/test', methods=['GET'])
def test_endpoint():
    return jsonify({
        "status": "success",
        "message": "API is working correctly",
        "timestamp": "2025-05-06 10:24:01"
    })

# The handler for Vercel
app = flask_app
