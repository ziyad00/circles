#!/usr/bin/env python3

import requests
import json

def test_user_update():
    base_url = "http://circles-alb-1949181177.us-east-1.elb.amazonaws.com"
    
    # Test the endpoint without authentication (should get 401)
    print("Testing PUT /users/me without authentication...")
    update_data = {
        "name": "Test Name",
        "bio": "Test Bio"
    }
    
    response = requests.put(f"{base_url}/users/me", json=update_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    # Test with invalid JSON (should get 422)
    print("\nTesting with invalid data...")
    invalid_data = {
        "name": "x" * 200,  # Exceeds max_length=100
        "bio": "x" * 600    # Exceeds max_length=500
    }
    
    response = requests.put(f"{base_url}/users/me", json=invalid_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

if __name__ == "__main__":
    test_user_update()
