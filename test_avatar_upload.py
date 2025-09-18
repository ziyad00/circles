#!/usr/bin/env python3

import requests
import json

# Test the avatar upload endpoint
def test_avatar_upload():
    base_url = "http://circles-alb-1949181177.us-east-1.elb.amazonaws.com"
    
    # First, let's try to test with a sample JWT token for user ziyad0
    # We'll need to check if we can find this user in the system first
    
    # Check if health endpoint is working
    print("Testing health endpoint...")
    health_response = requests.get(f"{base_url}/health")
    print(f"Health status: {health_response.status_code}")
    if health_response.status_code == 200:
        print(f"Health response: {health_response.json()}")
    
    # Test avatar upload endpoint without authentication (should get 401)
    print("\nTesting avatar upload without auth (should fail with 401)...")
    test_file = {
        'file': ('test.jpg', b'fake_image_data', 'image/jpeg')
    }
    
    upload_response = requests.post(f"{base_url}/users/me/avatar", files=test_file)
    print(f"Avatar upload status: {upload_response.status_code}")
    print(f"Avatar upload response: {upload_response.text}")
    
    # Test with HEIC content type (our recent fix)
    print("\nTesting HEIC content type validation...")
    heic_file = {
        'file': ('test.heic', b'fake_heic_data', 'image/heic')
    }
    
    heic_response = requests.post(f"{base_url}/users/me/avatar", files=heic_file)
    print(f"HEIC upload status: {heic_response.status_code}")
    print(f"HEIC upload response: {heic_response.text}")

if __name__ == "__main__":
    test_avatar_upload()
