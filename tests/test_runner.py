#!/usr/bin/env python3
"""
Test runner for the KGLW Manager test suite.
Provides convenient commands for running different test categories.
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and display results."""
    print(f"\n{'='*60}")
    print(f"🧪 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=False)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run KGLW Manager tests")
    parser.add_argument('--unit', action='store_true', help='Run unit tests only')
    parser.add_argument('--integration', action='store_true', help='Run integration tests only')
    parser.add_argument('--api', action='store_true', help='Run API tests only (requires network)')
    parser.add_argument('--slow', action='store_true', help='Include slow tests')
    parser.add_argument('--requires-collection', action='store_true', help='Run tests that need real collection')
    parser.add_argument('--coverage', action='store_true', help='Run with coverage reporting')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--parallel', '-n', type=int, help='Run tests in parallel (requires pytest-xdist)')
    
    args = parser.parse_args()
    
    # Base pytest command
    base_cmd = "uv run python -m pytest"
    
    # Add test path
    base_cmd += " tests/"
    
    # Add markers based on arguments
    markers = []
    if args.unit:
        markers.append("unit")
    if args.integration:
        markers.append("integration")
    if args.api:
        markers.append("api")
    else:
        # Skip API tests by default unless specifically requested
        markers.append("not api")
    
    if not args.slow:
        markers.append("not slow")
    
    if not args.requires_collection:
        markers.append("not requires_collection")
    
    if markers:
        base_cmd += f" -m '{' and '.join(markers)}'"
    
    # Add coverage if requested
    if args.coverage:
        base_cmd += " --cov=kglw_manager --cov-report=html --cov-report=term"
    
    # Add verbose output
    if args.verbose:
        base_cmd += " -v"
    
    # Add parallel execution
    if args.parallel:
        base_cmd += f" -n {args.parallel}"
    
    print("🎸 KGLW Manager Test Suite")
    print("=" * 40)
    
    if not any([args.unit, args.integration, args.api]):
        print("Running all tests (excluding API and slow tests by default)")
    else:
        test_types = []
        if args.unit:
            test_types.append("unit")
        if args.integration:
            test_types.append("integration")
        if args.api:
            test_types.append("API")
        print(f"Running: {', '.join(test_types)} tests")
    
    success = run_command(base_cmd, "Test Execution")
    
    if success:
        print(f"\n🎉 All tests passed!")
        if args.coverage:
            print("📊 Coverage report generated in htmlcov/")
    else:
        print(f"\n⚠️ Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()