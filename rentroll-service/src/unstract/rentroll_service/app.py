import logging

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from helper import extract_rent_roll
from json_repair import repair_json

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/api/extract-rentrolls", methods=["POST"])
async def handle_extract():
    """API endpoint to extract rent roll data from raw text.
    Expects a JSON payload with 'schema' and 'extracted_data'.
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    schema = data.get("schema")
    extracted_data = data.get("text")
    llm_config = data.get("llm_config")
    prompt = schema
    schema = repair_json(json_str=prompt, return_objects=True)
    if isinstance(schema, str):
        raise ValueError("Prompt entered is not a valid JSON.")
    if not schema or not extracted_data:
        raise ValueError("Missing 'schema' or 'extracted_data' in request body")

    try:
        logger.info("Received request to extract rent roll data.")
        result = await extract_rent_roll(
            schema=schema,
            extracted_data=extracted_data,
            llm_config=llm_config,
        )
        logger.info("Successfully extracted rent roll data.")
        return jsonify(result)
    except Exception as e:
        logger.error(f"An error occurred during extraction: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred.", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5003)
