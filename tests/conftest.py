"""
Add scripts/ to sys.path so test modules can import scripts directly.
This file is automatically picked up by the unittest runner when placed
in the tests/ directory.
"""
import sys
import os

scripts_dir = os.path.join(os.path.dirname(__file__), '..', 'scripts')
if scripts_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(scripts_dir))
