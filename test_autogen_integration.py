#!/usr/bin/env python3
"""Test script for the real AutoGen integration endpoint."""

import json
import requests
import time

def test_autogen_integration():
    """Test the real AutoGen integration endpoint."""
    
    # Assuming prompt service runs on port 3003 (default from pyproject.toml)
    base_url = "http://localhost:3003"
    
    print("=" * 60)
    print("TESTING REAL AUTOGEN INTEGRATION")
    print("=" * 60)
    
    # Test 1: Health check
    print("\n1. Testing AutoGen health endpoint...")
    try:
        response = requests.get(f"{base_url}/autogen-health", timeout=10)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: GET request with default parameters
    print("\n2. Testing real AutoGen endpoint (GET)...")
    try:
        response = requests.get(f"{base_url}/test-real-autogen", timeout=30)
        print(f"   Status: {response.status_code}")
        result = response.json()
        print(f"   Success: {result.get('success')}")
        if result.get('success'):
            print(f"   Adapter ID: {result.get('adapter_instance_id')}")
            print(f"   Tests run: {list(result.get('tests', {}).keys())}")
            print(f"   Total tokens: {result.get('total_tokens_used')}")
        else:
            print(f"   Error: {result.get('error')}")
            print(f"   Troubleshooting: {result.get('troubleshooting', {})}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 3: POST request with custom parameters
    print("\n3. Testing real AutoGen endpoint (POST)...")
    test_payload = {
        "prompt": "What is 5 + 7? Answer in one word.",
        "context": "Simple arithmetic",
        "streaming": False,
        "test_scenarios": ["completion"]
    }
    
    try:
        response = requests.post(
            f"{base_url}/test-real-autogen",
            json=test_payload,
            timeout=30
        )
        print(f"   Status: {response.status_code}")
        result = response.json()
        print(f"   Success: {result.get('success')}")
        if result.get('success'):
            basic_test = result.get('tests', {}).get('basic_completion', {})
            print(f"   Prompt: {basic_test.get('prompt')}")
            print(f"   Response: {basic_test.get('response')}")
            print(f"   Tokens used: {basic_test.get('usage', {}).get('total_tokens')}")
        else:
            print(f"   Error: {result.get('error')}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 4: POST request with streaming
    print("\n4. Testing real AutoGen endpoint (POST with streaming)...")
    streaming_payload = {
        "prompt": "Paris",
        "streaming": True,
        "test_scenarios": ["completion", "streaming"]
    }
    
    try:
        response = requests.post(
            f"{base_url}/test-real-autogen",
            json=streaming_payload,
            timeout=45
        )
        print(f"   Status: {response.status_code}")
        result = response.json()
        print(f"   Success: {result.get('success')}")
        if result.get('success'):
            streaming_test = result.get('tests', {}).get('streaming_completion', {})
            print(f"   Chunks received: {streaming_test.get('chunks_received')}")
            print(f"   Response length: {len(streaming_test.get('total_response', ''))}")
        else:
            print(f"   Error: {result.get('error')}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n" + "=" * 60)
    print("TESTING COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_autogen_integration()