#!/usr/bin/env python3
"""
Debug script to check what endpoints are being found
"""

import re
from pathlib import Path

def check_router_file(file_path):
    """Check what endpoints are found in a router file."""
    print(f"\n🔍 Checking {file_path}")
    
    if not file_path.exists():
        print(f"❌ File does not exist: {file_path}")
        return
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
            
        endpoints_found = []
        for i, line in enumerate(lines, 1):
            # Match @router.get, @router.post, etc.
            match = re.search(r'@router\.(get|post|put|delete|patch)\("([^"]+)"', line)
            if match:
                method = match.group(1).upper()
                path = match.group(2)
                endpoints_found.append((method, path, i))
                print(f"  ✅ {method} {path} (line {i})")
        
        print(f"  📊 Total endpoints found: {len(endpoints_found)}")
        return endpoints_found
        
    except Exception as e:
        print(f"❌ Error reading {file_path}: {e}")
        return []

def main():
    project_root = Path(__file__).parent.parent
    backend_path = project_root / "circles"
    
    router_files = [
        "app/routers/users.py",
        "app/routers/places.py", 
        "app/routers/collections.py",
        "app/routers/follow.py",
        "app/routers/dms.py",
        "app/routers/auth.py",
        "app/routers/onboarding.py",
        "app/routers/health.py",
        "app/routers/dms_ws.py",
    ]
    
    all_endpoints = []
    for router_file in router_files:
        file_path = backend_path / router_file
        endpoints = check_router_file(file_path)
        all_endpoints.extend(endpoints)
    
    print(f"\n📊 Total endpoints across all routers: {len(all_endpoints)}")
    
    # Check for specific endpoints that should exist
    expected_endpoints = [
        ("POST", "/request-otp"),
        ("POST", "/verify-otp"),
        ("POST", "/check-username"),
        ("POST", "/complete-setup"),
        ("GET", "/me"),
    ]
    
    print(f"\n🔍 Checking for expected endpoints:")
    for method, path in expected_endpoints:
        found = any(ep[0] == method and ep[1] == path for ep in all_endpoints)
        status = "✅" if found else "❌"
        print(f"  {status} {method} {path}")

if __name__ == "__main__":
    main()
