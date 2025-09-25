#!/usr/bin/env python3
"""
API Call Analysis Script

This script analyzes frontend API calls and compares them with backend endpoints
to identify mismatches, missing endpoints, and potential errors.
"""

import os
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ApiEndpoint:
    method: str
    path: str
    response_model: Optional[str] = None
    file_path: str = ""
    line_number: int = 0

@dataclass
class FrontendApiCall:
    endpoint: str
    method: str
    file_path: str
    line_number: int
    usage_context: str = ""

class ApiAnalyzer:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.frontend_path = self.project_root / "frontend"
        self.backend_path = self.project_root / "circles"
        
        self.backend_endpoints: List[ApiEndpoint] = []
        self.frontend_calls: List[FrontendApiCall] = []
        self.api_endpoints_constants: Dict[str, str] = {}
        
    def analyze_backend_endpoints(self):
        """Extract all backend API endpoints from router files."""
        print("🔍 Analyzing backend endpoints...")
        
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
        
        for router_file in router_files:
            file_path = self.backend_path / router_file
            if file_path.exists():
                self._extract_endpoints_from_file(file_path)
        
        print(f"✅ Found {len(self.backend_endpoints)} backend endpoints")
    
    def _extract_endpoints_from_file(self, file_path: Path):
        """Extract endpoints from a single router file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Extract router prefix
            prefix = ""
            for line in lines:
                prefix_match = re.search(r'APIRouter\([^)]*prefix=["\']([^"\']+)["\']', line)
                if prefix_match:
                    prefix = prefix_match.group(1)
                    break
                
            for i, line in enumerate(lines, 1):
                # Match @router.get, @router.post, etc.
                match = re.search(r'@router\.(get|post|put|delete|patch)\("([^"]+)"', line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)
                    
                    # Add prefix to path
                    full_path = prefix + path if prefix else path
                    
                    # Look for response_model in the same line or next few lines
                    response_model = None
                    for j in range(i, min(i + 3, len(lines))):
                        response_match = re.search(r'response_model=([^,\)]+)', lines[j])
                        if response_match:
                            response_model = response_match.group(1).strip()
                            break
                    
                    endpoint = ApiEndpoint(
                        method=method,
                        path=full_path,
                        response_model=response_model,
                        file_path=str(file_path.relative_to(self.project_root)),
                        line_number=i
                    )
                    self.backend_endpoints.append(endpoint)
                    
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
    
    def analyze_frontend_api_calls(self):
        """Extract all frontend API calls."""
        print("🔍 Analyzing frontend API calls...")
        
        # First, extract API endpoint constants
        self._extract_api_constants()
        
        # Then find all API calls
        dart_files = list(self.frontend_path.rglob("*.dart"))
        for dart_file in dart_files:
            if dart_file.is_file():  # Skip directories
                self._extract_api_calls_from_file(dart_file)
        
        print(f"✅ Found {len(self.frontend_calls)} frontend API calls")
    
    def _extract_api_constants(self):
        """Extract API endpoint constants from ApiEndpoints class."""
        api_endpoints_file = self.frontend_path / "lib/scr/core/utilities/constant/apiEndpoints.dart"
        
        if not api_endpoints_file.exists():
            print("❌ ApiEndpoints.dart not found")
            return
        
        try:
            with open(api_endpoints_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Extract static const String definitions
            pattern = r'static const String (\w+) = \'([^\']+)\';'
            matches = re.findall(pattern, content)
            
            for name, endpoint in matches:
                self.api_endpoints_constants[name] = endpoint
                
            print(f"✅ Found {len(self.api_endpoints_constants)} API endpoint constants")
            
        except Exception as e:
            print(f"❌ Error reading ApiEndpoints.dart: {e}")
    
    def _extract_api_calls_from_file(self, file_path: Path):
        """Extract API calls from a single Dart file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            for i, line in enumerate(lines, 1):
                # Look for ApiEndpoints. usage
                api_matches = re.finditer(r'ApiEndpoints\.(\w+)', line)
                for match in api_matches:
                    constant_name = match.group(1)
                    if constant_name in self.api_endpoints_constants:
                        endpoint = self.api_endpoints_constants[constant_name]
                        
                        # Determine HTTP method from context
                        method = self._determine_http_method(line, lines, i)
                        
                        api_call = FrontendApiCall(
                            endpoint=endpoint,
                            method=method,
                            file_path=str(file_path.relative_to(self.project_root)),
                            line_number=i,
                            usage_context=line.strip()
                        )
                        self.frontend_calls.append(api_call)
                        
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
    
    def _determine_http_method(self, line: str, lines: List[str], line_num: int) -> str:
        """Determine HTTP method from context."""
        # Look for method calls in the same line or nearby lines
        context_lines = lines[max(0, line_num-3):line_num+3]
        context = ' '.join(context_lines)
        
        if '.get(' in context:
            return 'GET'
        elif '.post(' in context:
            return 'POST'
        elif '.put(' in context:
            return 'PUT'
        elif '.delete(' in context:
            return 'DELETE'
        elif '.patch(' in context:
            return 'PATCH'
        else:
            return 'UNKNOWN'
    
    def find_mismatches(self) -> Dict[str, List[str]]:
        """Find mismatches between frontend calls and backend endpoints."""
        print("🔍 Finding API mismatches...")
        
        mismatches = {
            'missing_backend_endpoints': [],
            'missing_frontend_calls': [],
            'method_mismatches': [],
            'path_mismatches': []
        }
        
        # Create sets for easier comparison
        backend_paths = {(ep.method, ep.path) for ep in self.backend_endpoints}
        frontend_paths = {(call.method, call.endpoint) for call in self.frontend_calls}
        
        # Find frontend calls without corresponding backend endpoints
        for call in self.frontend_calls:
            if (call.method, call.endpoint) not in backend_paths:
                # Check for similar paths (with parameters)
                similar_found = False
                for bep in self.backend_endpoints:
                    if self._paths_similar(call.endpoint, bep.path):
                        similar_found = True
                        if call.method != bep.method:
                            mismatches['method_mismatches'].append({
                                'frontend': f"{call.method} {call.endpoint}",
                                'backend': f"{bep.method} {bep.path}",
                                'frontend_file': call.file_path,
                                'backend_file': bep.file_path
                            })
                        break
                
                if not similar_found:
                    mismatches['missing_backend_endpoints'].append({
                        'endpoint': f"{call.method} {call.endpoint}",
                        'file': call.file_path,
                        'line': call.line_number,
                        'context': call.usage_context
                    })
        
        # Find backend endpoints without corresponding frontend calls
        for endpoint in self.backend_endpoints:
            if (endpoint.method, endpoint.path) not in frontend_paths:
                # Check if it's a parameterized endpoint that might be used
                has_similar_frontend = any(
                    self._paths_similar(endpoint.path, call.endpoint)
                    for call in self.frontend_calls
                )
                
                if not has_similar_frontend:
                    mismatches['missing_frontend_calls'].append({
                        'endpoint': f"{endpoint.method} {endpoint.path}",
                        'file': endpoint.file_path,
                        'line': endpoint.line_number,
                        'response_model': endpoint.response_model
                    })
        
        return mismatches
    
    def _paths_similar(self, path1: str, path2: str) -> bool:
        """Check if two paths are similar (accounting for parameters)."""
        # Remove parameters for comparison
        clean_path1 = re.sub(r'\{[^}]+\}', '{}', path1)
        clean_path2 = re.sub(r'\{[^}]+\}', '{}', path2)
        return clean_path1 == clean_path2
    
    def generate_report(self, mismatches: Dict[str, List[str]]) -> str:
        """Generate a comprehensive API analysis report."""
        report = []
        report.append("# API Call Analysis Report")
        report.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Summary
        report.append("## Summary")
        report.append(f"- Backend endpoints: {len(self.backend_endpoints)}")
        report.append(f"- Frontend API calls: {len(self.frontend_calls)}")
        report.append(f"- Missing backend endpoints: {len(mismatches['missing_backend_endpoints'])}")
        report.append(f"- Missing frontend calls: {len(mismatches['missing_frontend_calls'])}")
        report.append(f"- Method mismatches: {len(mismatches['method_mismatches'])}")
        report.append("")
        
        # Missing backend endpoints
        if mismatches['missing_backend_endpoints']:
            report.append("## ❌ Missing Backend Endpoints")
            report.append("These frontend calls don't have corresponding backend endpoints:")
            report.append("")
            for item in mismatches['missing_backend_endpoints']:
                report.append(f"### {item['endpoint']}")
                report.append(f"- **File:** `{item['file']}:{item['line']}`")
                report.append(f"- **Context:** `{item['context']}`")
                report.append("")
        
        # Missing frontend calls
        if mismatches['missing_frontend_calls']:
            report.append("## ⚠️ Unused Backend Endpoints")
            report.append("These backend endpoints don't have corresponding frontend calls:")
            report.append("")
            for item in mismatches['missing_frontend_calls']:
                report.append(f"### {item['endpoint']}")
                report.append(f"- **File:** `{item['file']}:{item['line']}`")
                if item['response_model']:
                    report.append(f"- **Response Model:** `{item['response_model']}`")
                report.append("")
        
        # Method mismatches
        if mismatches['method_mismatches']:
            report.append("## 🔄 Method Mismatches")
            report.append("These endpoints have method mismatches between frontend and backend:")
            report.append("")
            for item in mismatches['method_mismatches']:
                report.append(f"### {item['frontend']} vs {item['backend']}")
                report.append(f"- **Frontend:** `{item['frontend_file']}`")
                report.append(f"- **Backend:** `{item['backend_file']}`")
                report.append("")
        
        # All backend endpoints
        report.append("## 📋 All Backend Endpoints")
        report.append("")
        for endpoint in sorted(self.backend_endpoints, key=lambda x: (x.method, x.path)):
            report.append(f"- **{endpoint.method}** `{endpoint.path}`")
            if endpoint.response_model:
                report.append(f"  - Response: `{endpoint.response_model}`")
            report.append(f"  - File: `{endpoint.file_path}:{endpoint.line_number}`")
            report.append("")
        
        # All frontend calls
        report.append("## 📱 All Frontend API Calls")
        report.append("")
        for call in sorted(self.frontend_calls, key=lambda x: (x.method, x.endpoint)):
            report.append(f"- **{call.method}** `{call.endpoint}`")
            report.append(f"  - File: `{call.file_path}:{call.line_number}`")
            report.append(f"  - Context: `{call.usage_context}`")
            report.append("")
        
        return "\n".join(report)
    
    def generate_api_spec(self) -> Dict:
        """Generate a JSON API specification."""
        spec = {
            "info": {
                "title": "Circles API",
                "version": "1.0.0",
                "description": "Auto-generated API specification",
                "generated_at": datetime.now().isoformat()
            },
            "endpoints": []
        }
        
        for endpoint in self.backend_endpoints:
            endpoint_spec = {
                "method": endpoint.method,
                "path": endpoint.path,
                "response_model": endpoint.response_model,
                "file": endpoint.file_path,
                "line": endpoint.line_number
            }
            spec["endpoints"].append(endpoint_spec)
        
        return spec
    
    def run_analysis(self):
        """Run the complete API analysis."""
        print("🚀 Starting API Call Analysis...")
        print("=" * 50)
        
        # Analyze backend and frontend
        self.analyze_backend_endpoints()
        self.analyze_frontend_api_calls()
        
        # Find mismatches
        mismatches = self.find_mismatches()
        
        # Generate reports
        report = self.generate_report(mismatches)
        api_spec = self.generate_api_spec()
        
        # Save reports
        report_file = self.project_root / "API_ANALYSIS_REPORT.md"
        spec_file = self.project_root / "api_spec.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        with open(spec_file, 'w', encoding='utf-8') as f:
            json.dump(api_spec, f, indent=2)
        
        print("=" * 50)
        print("✅ Analysis complete!")
        print(f"📄 Report saved to: {report_file}")
        print(f"📋 API spec saved to: {spec_file}")
        
        # Print summary
        print("\n📊 Summary:")
        print(f"- Backend endpoints: {len(self.backend_endpoints)}")
        print(f"- Frontend API calls: {len(self.frontend_calls)}")
        print(f"- Missing backend endpoints: {len(mismatches['missing_backend_endpoints'])}")
        print(f"- Missing frontend calls: {len(mismatches['missing_frontend_calls'])}")
        print(f"- Method mismatches: {len(mismatches['method_mismatches'])}")
        
        return mismatches

def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    analyzer = ApiAnalyzer(project_root)
    mismatches = analyzer.run_analysis()
    
    # Exit with error code if there are critical issues
    if mismatches['missing_backend_endpoints']:
        print("\n❌ Critical issues found! Check the report for details.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
