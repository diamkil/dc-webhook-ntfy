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
    for condition in filters:
        if 'and' in condition:
            if all(check_filter(data, f) for f in condition['and']):
                matched_filter = next((f for f in condition['and'] if 'format' in f), None)
                format = matched_filter.get('format') if matched_filter else None
                title = matched_filter.get('title', "")
                return True, format, title
        if 'or' in condition:
            if any(check_filter(data, f) for f in condition['or']):
                matched_filter = next(f for f in condition['or'] if check_filter(data, f))
                format = matched_filter.get('format', None)
                title = matched_filter.get('title', "")
                return True, format, title
    return True, None, ""

def check_filter(data, f):
    keys = f['key'].split('.')
    value = data
    for key in keys:
        value = value.get(key, None)
        if value is None or value != f['value']:
            return False
    if 'discard' in f and f['discard']:
        return False  # Discard the message
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
    topic_config = config['topics'].get(topic, {"filters": [], "format": "{{raw_message}}", "title": ""})

    # Apply filters
    filters = topic_config.get('filters', [])
    matched, custom_format, custom_title = apply_filters(data, filters)

    if not matched and custom_format is None:
        logger.info(f"Discarding message for topic {topic} based on filters: {data}")
        return jsonify(success=False, message="Message discarded by filter")

    format_str = custom_format or topic_config.get('format', "{{raw_message}}")
    title_str = custom_title or topic_config.get('title', "")
    formatted_message = format_message(data, format_str)
    logger.info(f"Formatted message for topic {topic}: {formatted_message}")

    # Send to ntfy
    ntfy_url = f"{NTFY_URL_BASE}/{topic}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "title": title_str,
        "message": formatted_message
    }
    response = requests.post(ntfy_url, headers=headers, json=payload)
    if response.status_code == 200:
        logger.info(f"Successfully sent message to ntfy topic {topic}")
        return jsonify(success=True)
    else:
        logger.error(f"Failed to send message to ntfy topic {topic}, status code: {response.status_code}")
        return jsonify(success=False, status_code=response.status_code)

if __name__ == '__main__':
    logger.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=5000)
