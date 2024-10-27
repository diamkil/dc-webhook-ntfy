from flask import Flask, request, jsonify
import requests
import yaml
import os
import logging
import json
import re

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
    if 'key_not_defined' in f:
        keys = f['key_not_defined'].split('.')
        value = data
        for key in keys:
            value = value.get(key, None)
            if value is not None:
                return False  # Key is defined, so the condition fails
        return True  # Key is not defined, so the condition passes
    elif 'key' in f:
        keys = f['key'].split('.')
        value = data
        for key in keys:
            value = value.get(key, None)
            if value is None:
                return False  # Key is not found, so the condition fails
        # If `value` is not specified, accept any value as long as key exists
        if 'value' in f:
            return value == f['value']  # Compare only if `value` is specified
        return True  # `key` exists, and no specific `value` to check, so it passes
    return False

def format_message(data, format_str):
    data['raw_message'] = json.dumps(data)  # Add the raw message to the data
    message = format_str
    
    # Regular expression to match loop syntax, e.g., {{loop:item in items:[{{item.property}}]}}
    loop_pattern = r"\{\{loop:(\w+)\s+in\s+(\w+):\[(.*?)\]\}\}"
    loops = re.findall(loop_pattern, format_str)

    for loop_var, list_key, loop_template in loops:
        if list_key in data and isinstance(data[list_key], list):
            formatted_items = []
            for item in data[list_key]:
                item_message = loop_template
                for key, value in item.items():
                    item_message = item_message.replace(f"{{{{{loop_var}.{key}}}}}", str(value))
                formatted_items.append(item_message)
            loop_result = "\n".join(formatted_items)
            message = message.replace(f"{{{{loop:{loop_var} in {list_key}:[{loop_template}]}}}}", loop_result)

    # Replace other placeholders
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
        "Content-Type": "text/plain",
        "Title": title_str
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
