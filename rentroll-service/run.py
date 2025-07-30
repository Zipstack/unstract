import logging
from unstract.rentroll_service.app import app

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=5003, debug=True)
