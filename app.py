from flask import Flask, request, jsonify
import requests
import yaml
import os
import logging
import json

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
    data['raw_message'] = json.dumps(data)  # Add the raw message to the data
    message = format_str
    for key, value in data.items():
        placeholder = f"{{{{{key}}}}}"
        message = message.replace(placeholder, str(value))
    return message

@app.route('/webhook/<topic>', methods=['POST'])
def webhook(topic):
    data = request.json
    logger.info(f"Received data for topic {topic}: {data}")
    topic_config = config['topics'].get(topic, {"filters": [], "format": "{{raw_message}}"})

    # Apply filters
    filters = topic_config.get('filters', [])
    if not apply_filters(data, filters):
        logger.warning(f"Filters not matched for topic {topic} with data: {data}")
        return jsonify(success=False, message="Filters not matched")

    # Format message
    formatted_message = format_message(data, topic_config.get('format', '{{raw_message}}'))
    logger.info(f"Formatted message for topic {topic}: {formatted_message}")

    # Send to ntfy
    ntfy_url = f"{NTFY_URL_BASE}/{topic}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "text/plain"
    }
    response = requests.post(ntfy_url, headers=headers, data=formatted_message)
    if response.status_code == 200:
        logger.info(f"Successfully sent message to ntfy topic {topic}")
        return jsonify(success=True)
    else:
        logger.error(f"Failed to send message to ntfy topic {topic}, status code: {response.status_code}")
        return jsonify(success=False, status_code=response.status_code)

if __name__ == '__main__':
    logger.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=5000)
