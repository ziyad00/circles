#!/usr/bin/env python3
"""
Enhanced API Call Analysis Script

This script analyzes frontend API calls with request bodies and compares them with backend endpoints
to identify missing endpoints, mismatched schemas, and potential errors.
"""

import os
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class ApiEndpoint:
    method: str
    path: str
    response_model: Optional[str] = None
    request_model: Optional[str] = None
    file_path: str = ""
    line_number: int = 0
    description: str = ""


@dataclass
class FrontendApiCall:
    endpoint: str
    method: str
    file_path: str
    line_number: int
    usage_context: str = ""
    request_body: Optional[str] = None
    query_params: Optional[str] = None
    headers: Optional[str] = None
    response_handling: Optional[str] = None


@dataclass
class RequestModel:
    name: str
    fields: Dict[str, str]  # field_name -> field_type
    file_path: str
    line_number: int


class EnhancedApiAnalyzer:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.frontend_path = self.project_root / "frontend"
        self.backend_path = self.project_root / "circles"

        self.backend_endpoints: List[ApiEndpoint] = []
        self.frontend_calls: List[FrontendApiCall] = []
        self.api_endpoints_constants: Dict[str, str] = {}
        self.request_models: List[RequestModel] = []

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

            # Extract router prefix - handle multi-line APIRouter definitions
            prefix = ""
            for i, line in enumerate(lines):
                if 'APIRouter(' in line:
                    # Look for prefix in the same line or next few lines
                    for j in range(i, min(i + 10, len(lines))):
                        prefix_match = re.search(
                            r'prefix=["\']([^"\']+)["\']', lines[j])
                        if prefix_match:
                            prefix = prefix_match.group(1)
                            break
                    if prefix:
                        break

            for i, line in enumerate(lines, 1):
                # Match @router.get, @router.post, etc.
                match = re.search(
                    r'@router\.(get|post|put|delete|patch)\("([^"]+)"', line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)

                    # Add prefix to path
                    full_path = prefix + path if prefix else path

                    # Look for response_model and request model in the function definition
                    response_model = None
                    request_model = None
                    description = ""

                    # Look in the next few lines for function definition
                    for j in range(i, min(i + 10, len(lines))):
                        # Check for response_model
                        response_match = re.search(
                            r'response_model=([^,\)]+)', lines[j])
                        if response_match:
                            response_model = response_match.group(1).strip()

                        # Check for request model (parameter with type annotation)
                        request_match = re.search(
                            r'(\w+):\s*(\w+Request|\w+Model|\w+Create|\w+Update)', lines[j])
                        if request_match and not request_model:
                            request_model = request_match.group(2)

                        # Extract docstring for description
                        if '"""' in lines[j] and not description:
                            # Look for the rest of the docstring
                            for k in range(j, min(j + 5, len(lines))):
                                if '"""' in lines[k] and k != j:
                                    description = lines[j:k+1]
                                    break

                    endpoint = ApiEndpoint(
                        method=method,
                        path=full_path,
                        response_model=response_model,
                        request_model=request_model,
                        file_path=str(
                            file_path.relative_to(self.project_root)),
                        line_number=i,
                        description=description
                    )
                    self.backend_endpoints.append(endpoint)

        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")

    def analyze_frontend_api_calls(self):
        """Extract all frontend API calls with request bodies."""
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
        api_endpoints_file = self.frontend_path / \
            "lib/scr/core/utilities/constant/apiEndpoints.dart"

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

            print(
                f"✅ Found {len(self.api_endpoints_constants)} API endpoint constants")

        except Exception as e:
            print(f"❌ Error reading ApiEndpoints.dart: {e}")

    def _extract_api_calls_from_file(self, file_path: Path):
        """Extract API calls from a single Dart file with request bodies."""
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

                        # Determine HTTP method and extract request details
                        method, request_body, query_params, headers, response_handling = self._extract_request_details(
                            line, lines, i, endpoint
                        )

                        api_call = FrontendApiCall(
                            endpoint=endpoint,
                            method=method,
                            file_path=str(
                                file_path.relative_to(self.project_root)),
                            line_number=i,
                            usage_context=line.strip(),
                            request_body=request_body,
                            query_params=query_params,
                            headers=headers,
                            response_handling=response_handling
                        )
                        self.frontend_calls.append(api_call)

        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")

    def _extract_request_details(self, line: str, lines: List[str], line_num: int, endpoint: str) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Extract HTTP method and request details from context."""
        # Look for method calls in the same line or nearby lines
        context_lines = lines[max(0, line_num-5):line_num+10]
        context = ' '.join(context_lines)

        method = "UNKNOWN"
        request_body = None
        query_params = None
        headers = None
        response_handling = None

        # Determine HTTP method
        if '.get(' in context:
            method = 'GET'
        elif '.post(' in context:
            method = 'POST'
        elif '.put(' in context:
            method = 'PUT'
        elif '.delete(' in context:
            method = 'DELETE'
        elif '.patch(' in context:
            method = 'PATCH'

        # Extract request body (data parameter)
        data_match = re.search(r'data:\s*([^,\)]+)', context)
        if data_match:
            request_body = data_match.group(1).strip()

        # Extract query parameters
        query_match = re.search(r'queryParameters:\s*([^,\)]+)', context)
        if query_match:
            query_params = query_match.group(1).strip()

        # Extract headers
        headers_match = re.search(r'headers:\s*([^,\)]+)', context)
        if headers_match:
            headers = headers_match.group(1).strip()

        # Extract response handling
        response_match = re.search(r'response\.data', context)
        if response_match:
            response_handling = "response.data"

        return method, request_body, query_params, headers, response_handling

    def find_missing_endpoints(self) -> Dict[str, List[Dict]]:
        """Find missing backend endpoints and analyze request/response mismatches."""
        print("🔍 Finding missing endpoints and analyzing mismatches...")

        issues = {
            'missing_backend_endpoints': [],
            'missing_frontend_calls': [],
            'method_mismatches': [],
            'request_body_mismatches': [],
            'response_model_mismatches': []
        }

        # Create sets for easier comparison
        backend_paths = {(ep.method, ep.path) for ep in self.backend_endpoints}
        frontend_paths = {(call.method, call.endpoint)
                          for call in self.frontend_calls}

        # Find frontend calls without corresponding backend endpoints
        for call in self.frontend_calls:
            if (call.method, call.endpoint) not in backend_paths:
                # Check for similar paths (with parameters)
                similar_found = False
                for bep in self.backend_endpoints:
                    if self._paths_similar(call.endpoint, bep.path):
                        similar_found = True
                        if call.method != bep.method:
                            issues['method_mismatches'].append({
                                'frontend': f"{call.method} {call.endpoint}",
                                'backend': f"{bep.method} {bep.path}",
                                'frontend_file': call.file_path,
                                'backend_file': bep.file_path,
                                'request_body': call.request_body
                            })
                        break

                if not similar_found:
                    issues['missing_backend_endpoints'].append({
                        'endpoint': f"{call.method} {call.endpoint}",
                        'file': call.file_path,
                        'line': call.line_number,
                        'context': call.usage_context,
                        'request_body': call.request_body,
                        'query_params': call.query_params,
                        'headers': call.headers
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
                    issues['missing_frontend_calls'].append({
                        'endpoint': f"{endpoint.method} {endpoint.path}",
                        'file': endpoint.file_path,
                        'line': endpoint.line_number,
                        'response_model': endpoint.response_model,
                        'request_model': endpoint.request_model,
                        'description': endpoint.description
                    })

        return issues

    def _paths_similar(self, path1: str, path2: str) -> bool:
        """Check if two paths are similar (accounting for parameters)."""
        # Remove parameters for comparison
        clean_path1 = re.sub(r'\{[^}]+\}', '{}', path1)
        clean_path2 = re.sub(r'\{[^}]+\}', '{}', path2)
        return clean_path1 == clean_path2

    def generate_detailed_report(self, issues: Dict[str, List[Dict]]) -> str:
        """Generate a comprehensive API analysis report."""
        report = []
        report.append("# Enhanced API Call Analysis Report")
        report.append(
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Summary
        report.append("## Summary")
        report.append(f"- Backend endpoints: {len(self.backend_endpoints)}")
        report.append(f"- Frontend API calls: {len(self.frontend_calls)}")
        report.append(
            f"- Missing backend endpoints: {len(issues['missing_backend_endpoints'])}")
        report.append(
            f"- Missing frontend calls: {len(issues['missing_frontend_calls'])}")
        report.append(
            f"- Method mismatches: {len(issues['method_mismatches'])}")
        report.append(
            f"- Request body mismatches: {len(issues['request_body_mismatches'])}")
        report.append("")

        # Missing backend endpoints (Critical Issues)
        if issues['missing_backend_endpoints']:
            report.append("## ❌ Critical: Missing Backend Endpoints")
            report.append(
                "These frontend calls don't have corresponding backend endpoints:")
            report.append("")
            for item in issues['missing_backend_endpoints']:
                report.append(f"### {item['endpoint']}")
                report.append(f"- **File:** `{item['file']}:{item['line']}`")
                report.append(f"- **Context:** `{item['context']}`")
                if item['request_body']:
                    report.append(
                        f"- **Request Body:** `{item['request_body']}`")
                if item['query_params']:
                    report.append(
                        f"- **Query Params:** `{item['query_params']}`")
                if item['headers']:
                    report.append(f"- **Headers:** `{item['headers']}`")
                report.append("")

        # Method mismatches
        if issues['method_mismatches']:
            report.append("## 🔄 Method Mismatches")
            report.append(
                "These endpoints have method mismatches between frontend and backend:")
            report.append("")
            for item in issues['method_mismatches']:
                report.append(f"### {item['frontend']} vs {item['backend']}")
                report.append(f"- **Frontend:** `{item['frontend_file']}`")
                report.append(f"- **Backend:** `{item['backend_file']}`")
                if item['request_body']:
                    report.append(
                        f"- **Request Body:** `{item['request_body']}`")
                report.append("")

        # Missing frontend calls
        if issues['missing_frontend_calls']:
            report.append("## ⚠️ Unused Backend Endpoints")
            report.append(
                "These backend endpoints don't have corresponding frontend calls:")
            report.append("")
            for item in issues['missing_frontend_calls']:
                report.append(f"### {item['endpoint']}")
                report.append(f"- **File:** `{item['file']}:{item['line']}`")
                if item['response_model']:
                    report.append(
                        f"- **Response Model:** `{item['response_model']}`")
                if item['request_model']:
                    report.append(
                        f"- **Request Model:** `{item['request_model']}`")
                if item['description']:
                    report.append(
                        f"- **Description:** `{item['description'][:100]}...`")
                report.append("")

        # All backend endpoints with details
        report.append("## 📋 All Backend Endpoints")
        report.append("")
        for endpoint in sorted(self.backend_endpoints, key=lambda x: (x.method, x.path)):
            report.append(f"- **{endpoint.method}** `{endpoint.path}`")
            if endpoint.response_model:
                report.append(f"  - Response: `{endpoint.response_model}`")
            if endpoint.request_model:
                report.append(f"  - Request: `{endpoint.request_model}`")
            report.append(
                f"  - File: `{endpoint.file_path}:{endpoint.line_number}`")
            report.append("")

        # All frontend calls with details
        report.append("## 📱 All Frontend API Calls")
        report.append("")
        for call in sorted(self.frontend_calls, key=lambda x: (x.method, x.endpoint)):
            report.append(f"- **{call.method}** `{call.endpoint}`")
            report.append(f"  - File: `{call.file_path}:{call.line_number}`")
            if call.request_body:
                report.append(f"  - Request Body: `{call.request_body}`")
            if call.query_params:
                report.append(f"  - Query Params: `{call.query_params}`")
            report.append(f"  - Context: `{call.usage_context}`")
            report.append("")

        return "\n".join(report)

    def generate_api_spec(self) -> Dict:
        """Generate a detailed JSON API specification."""
        spec = {
            "info": {
                "title": "Circles API",
                "version": "1.0.0",
                "description": "Enhanced API specification with request/response details",
                "generated_at": datetime.now().isoformat()
            },
            "endpoints": [],
            "frontend_calls": []
        }

        for endpoint in self.backend_endpoints:
            endpoint_spec = {
                "method": endpoint.method,
                "path": endpoint.path,
                "response_model": endpoint.response_model,
                "request_model": endpoint.request_model,
                "file": endpoint.file_path,
                "line": endpoint.line_number,
                "description": endpoint.description
            }
            spec["endpoints"].append(endpoint_spec)

        for call in self.frontend_calls:
            call_spec = {
                "method": call.method,
                "endpoint": call.endpoint,
                "file": call.file_path,
                "line": call.line_number,
                "request_body": call.request_body,
                "query_params": call.query_params,
                "headers": call.headers,
                "context": call.usage_context
            }
            spec["frontend_calls"].append(call_spec)

        return spec

    def run_analysis(self):
        """Run the complete enhanced API analysis."""
        print("🚀 Starting Enhanced API Call Analysis...")
        print("=" * 60)

        # Analyze backend and frontend
        self.analyze_backend_endpoints()
        self.analyze_frontend_api_calls()

        # Find issues
        issues = self.find_missing_endpoints()

        # Generate reports
        report = self.generate_detailed_report(issues)
        api_spec = self.generate_api_spec()

        # Save reports
        report_file = self.project_root / "ENHANCED_API_ANALYSIS_REPORT.md"
        spec_file = self.project_root / "enhanced_api_spec.json"

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)

        with open(spec_file, 'w', encoding='utf-8') as f:
            json.dump(api_spec, f, indent=2)

        print("=" * 60)
        print("✅ Enhanced analysis complete!")
        print(f"📄 Report saved to: {report_file}")
        print(f"📋 API spec saved to: {spec_file}")

        # Print summary
        print("\n📊 Summary:")
        print(f"- Backend endpoints: {len(self.backend_endpoints)}")
        print(f"- Frontend API calls: {len(self.frontend_calls)}")
        print(
            f"- Missing backend endpoints: {len(issues['missing_backend_endpoints'])}")
        print(
            f"- Missing frontend calls: {len(issues['missing_frontend_calls'])}")
        print(f"- Method mismatches: {len(issues['method_mismatches'])}")

        # Show critical issues
        if issues['missing_backend_endpoints']:
            print(f"\n❌ Critical Issues Found:")
            for item in issues['missing_backend_endpoints'][:5]:  # Show first 5
                print(f"  - {item['endpoint']} in {item['file']}")
            if len(issues['missing_backend_endpoints']) > 5:
                print(
                    f"  ... and {len(issues['missing_backend_endpoints']) - 5} more")

        return issues


def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    analyzer = EnhancedApiAnalyzer(project_root)
    issues = analyzer.run_analysis()

    # Exit with error code if there are critical issues
    if issues['missing_backend_endpoints']:
        print("\n❌ Critical issues found! Check the report for details.")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
