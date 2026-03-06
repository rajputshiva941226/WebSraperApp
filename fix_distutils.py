#!/usr/bin/env python3
"""
Fix for distutils compatibility issue in Python 3.12+
This script patches the missing distutils module
"""

import sys
import os

def create_distutils_patch():
    """Create a distutils compatibility patch"""
    
    # Create the distutils directory structure
    distutils_path = os.path.join(os.path.dirname(__file__), 'distutils')
    
    if not os.path.exists(distutils_path):
        os.makedirs(distutils_path)
    
    # Create __init__.py that imports from setuptools
    init_file = os.path.join(distutils_path, '__init__.py')
    with open(init_file, 'w') as f:
        f.write("""
# Compatibility patch for distutils in Python 3.12+
try:
    from setuptools._distutils import *
except ImportError:
    # Fallback for older Python versions
    import distutils as _distutils
    from _distutils import *
""")
    
    print(f"Created distutils patch at {distutils_path}")
    return distutils_path

if __name__ == "__main__":
    # Add current directory to Python path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    create_distutils_patch()
    print("Distutils compatibility patch installed")
