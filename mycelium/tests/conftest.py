import sys
import os

# Make the mycelium package root importable when running pytest from mycelium/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
