#  type: ignore
import logging
import os
import subprocess
import time
from typing import Any

import redis
from flask import Flask, request, send_file
from odf import teletype, text
from odf.opendocument import load

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s : %(message)s",
)

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/tmp/document_service/upload")
PROCESS_FOLDER = os.environ.get(
    "PROCESS_FOLDER", "/tmp/document_service/process"
)
LIBREOFFICE_PYTHON = os.environ.get("LIBREOFFICE_PYTHON", "/usr/bin/python3")
MAX_FILE_SIZE = int(
    os.environ.get("MAX_FILE_SIZE", 10485760)
)  # 10 * 1024 * 1024
SERVICE_API_TOKEN = os.environ.get("SERVICE_API_TOKEN", "")

app = Flask("document_service")
app.config["WTF_CSRF_ENABLED"] = False  # Sensitive


def authentication_middleware(func: Any) -> Any:
    def wrapper(*args, **kwargs):
        bearer_token = request.headers.get("Authorization")

        # Check if bearer token exists and validate it
        if not bearer_token or not validate_bearer_token(bearer_token):
            return "Unauthorized", 401

        return func(*args, **kwargs)

    return wrapper


def allowed_file_size(file: Any) -> bool:
    return file.content_length <= MAX_FILE_SIZE


def validate_bearer_token(token: Any) -> bool:
    key_status = None
    if token == SERVICE_API_TOKEN:
        key_status = True
    else:
        app.logger.error(f"Error while validating bearer token: {token}")
        key_status = False
    return key_status


@app.route("/health", methods=["GET"], endpoint="health_check")
def health_check():
    return "OK"


@app.route("/upload", methods=["POST"], endpoint="upload_file")
@authentication_middleware
def upload_file():
    """
    Sample Usage:
        curl -X POST -H "Authorization: 0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
        -F "file=@/Users/arun/Devel/pandora_storage/train_ticket.pdf" \
        http://localhost:3000/upload?file_name=file1.pdf&account_id=1234
    """

    if "file" not in request.files:
        app.logger.error("No file found!")
        return "No file found!", 400

    _file = request.files["file"]
    if _file.filename == "":
        app.logger.error("No selected file!")
        return "No selected file!", 400

    # Check file size
    content_length = request.headers.get("Content-Length", type=int)
    if content_length is not None and content_length > MAX_FILE_SIZE:
        app.logger.error(
            f"File size exceeds the limit! {content_length} > {MAX_FILE_SIZE}"
        )
        return "File size exceeds the limit!", 400

    account_id = request.args.get("account_id")
    file_name = request.args.get("file_name")
    app.logger.info(f"Uploading file {file_name} for account {account_id}")

    try:
        file_path = os.path.join(UPLOAD_FOLDER, f"{account_id}_{file_name}")
        _file.save(file_path)
    except Exception as e:
        app.logger.error(f"Error while saving file: {e}")
        return "Error while saving file!", 500

    try:
        # Store upload time in redis
        redis_host = os.environ.get("REDIS_HOST")
        redis_port = int(os.environ.get("REDIS_PORT"))
        redis_password = os.environ.get("REDIS_PASSWORD")
        r = redis.Redis(
            host=redis_host, port=redis_port, password=redis_password
        )
        # TODO: Create a file reaper process to look at uploaded time and delete
        redis_key = f"upload_time:{account_id}_{file_name}"
        current_timestamp = int(time.time())
        r.set(redis_key, current_timestamp)
        r.close()
    except Exception as e:
        app.logger.error(f"Error while storing upload time in redis: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return "Error while storing upload time in redis!", 500

    app.logger.info(f"File uploaded successfully! {file_path}")
    return "File uploaded successfully!", 200


@app.route("/find_and_replace", methods=["POST"], endpoint="find_and_replace")
@authentication_middleware
def find_and_replace():
    account_id = request.args.get("account_id")
    file_name = request.args.get("file_name")
    output_format = request.args.get("output_format").lower()
    find_and_replace_text = request.json

    app.logger.info(
        f"Find and replace for file {file_name} for account {account_id}"
    )
    app.logger.info(f"Output format: {output_format}")

    if output_format not in ["pdf"]:
        app.logger.error(f"Unsupported output format: {output_format}")
        return "Unsupported output format!", 400

    file_namex = os.path.join(UPLOAD_FOLDER, f"{account_id}_{file_name}")

    # Check if file exists
    if not os.path.exists(file_namex):
        app.logger.error(f"File not found! {file_namex}")
        return "File not found!", 400

    # Convert the orginal file to ODT format for processing
    file_name_odt = f"{account_id}_{file_name}.odt"
    file_name_odt = os.path.join(PROCESS_FOLDER, file_name_odt)
    try:
        command = f"{LIBREOFFICE_PYTHON} -m unoserver.converter \
            --convert-to odt --filter writer8 {file_namex} {file_name_odt}"
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True
        )
        app.logger.info(result)
        if result.returncode != 0:
            app.logger.error(
                f"Failed to convert file to ODT format: \
                             {result.stdout} | ERR: {result.stderr}"
            )
            return "Failed to convert file to ODT format!", 500
        else:
            app.logger.info(
                f"File converted to ODT format successfully! {file_name_odt}"
            )
            app.logger.info(
                f"ODT convertion result: {result.stdout} | {result.stderr}"
            )
    except Exception as e:
        app.logger.error(f"Error while converting file to ODT format: {e}")
        return "Error while converting file to ODT format!", 500

    # Find and replace
    doc = load(file_name_odt)
    for find_str in find_and_replace_text:
        app.logger.info(
            f"Find and replace: {find_str} -> {find_and_replace_text[find_str]}"
        )
        replace_str = find_and_replace_text[find_str]
        for element in doc.getElementsByType(text.Span):
            if find_str in teletype.extractText(element):
                app.logger.info(
                    f"Found {find_str} in {teletype.extractText(element)}"
                )
                new_element = text.Span()
                new_element.setAttribute(
                    "stylename", element.getAttribute("stylename")
                )
                t = teletype.extractText(element)
                t = t.replace(find_str, replace_str)
                new_element.addText(t)
                element.parentNode.insertBefore(new_element, element)
                element.parentNode.removeChild(element)
    doc.save(file_name_odt)

    file_name_output = f"{account_id}_{file_name}.{output_format}"
    file_name_output = os.path.join(PROCESS_FOLDER, file_name_output)

    # Convert the ODT file to the requested format
    try:
        command = (
            f"{LIBREOFFICE_PYTHON} -m unoserver.converter --convert-to pdf "
            f"--filter writer_pdf_Export {file_name_odt} {file_name_output}"
        )
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True
        )
        if result.returncode != 0:
            app.logger.error(
                f"Failed to convert file to {output_format} format: "
                f"{result.stdout} | ERR: {result.stderr}"
            )
            return "Failed to convert file to ODT format!", 500
        else:
            app.logger.info(
                f"File converted to {output_format} format successfully! "
                f"{file_name_output}"
            )
            app.logger.info(
                f"ODT convertion result: {result.stdout} | {result.stderr}"
            )
    except Exception as e:
        app.logger.error(
            f"Error while converting file to {output_format} format: {e}"
        )
        return f"Error while converting file to {output_format} format!", 500
    return send_file(file_name_output, as_attachment=True)


if __name__ == "__main__":
    # Check if upload folder exists and create it if not
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    if not os.path.exists(PROCESS_FOLDER):
        os.makedirs(PROCESS_FOLDER)

    # Start the server
    app.run()
