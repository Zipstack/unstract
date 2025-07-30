#!/usr/bin/env python
import os
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from unstract.rentroll_service.app import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
