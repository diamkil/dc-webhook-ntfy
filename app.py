from flask import Flask, request, jsonify
import requests
import yaml
import os
import logging

app = Flask(__name__)
API_KEY = os.getenv("NTFY_API_KEY")
NTFY_URL_BASE = os.getenv("NTFY_URL_BASE", "https://ntfy.sh")
CONFIG_FILE = "config.yml"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
with open(CONFIG_FILE, 'r') as file:
    config = yaml.safe_load(file)

def apply_filters(data, filters):
    for f in filters:
        keys = f['key'].split('.')
        value = data
        for key in keys:
            value = value.get(key, None)
            if value is None:
                return False
        if value != f['value']:
            return False
    return True

def format_message(data, format_str):
    message = format_str
    for key in extract_keys(data):
        placeholder = f"{{{{{key}}}}}"
        value = extract_value(data, key.split('.'))
        message = message.replace(placeholder, str(value))
    return message

def extract_keys(data, prefix=''):
    keys = []
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.extend(extract_keys(value, full_key))
        else:
            keys.append(full_key)
    return keys

def extract_value(data, keys):
    value = data
    for key in keys:
        value = value.get(key, None)
        if value is None:
            return ''
    return value

@app.route('/webhook/<topic>', methods=['POST'])
def webhook(topic):
    data = request.json
    logger.info(f"Received data for topic {topic}: {data}")
    topic_config = config['topics'].get(topic, {"filters": [], "format": "{{message}}"})

    # Apply filters
    filters = topic_config.get('filters', [])
    if not apply_filters(data, filters):
        logger.warning(f"Filters not matched for topic {topic} with data: {data}")
        return jsonify(success=False, message="Filters not matched")

    # Format message
    format_str = topic_config.get('format', "{{message}}")
    message = format_message(data, format_str)
    logger.info(f"Formatted message for topic {topic}: {message}")

    # Send to ntfy
    ntfy_url = f"{NTFY_URL_BASE}/{topic}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "text/plain"
    }
    response = requests.post(ntfy_url, headers=headers, data=message)
    if response.status_code == 200:
        logger.info(f"Successfully sent message to ntfy topic {topic}")
        return jsonify(success=True)
    else:
        logger.error(f"Failed to send message to ntfy topic {topic}, status code: {response.status_code}")
        return jsonify(success=False, status_code=response.status_code)

if __name__ == '__main__':
    logger.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=5000)
