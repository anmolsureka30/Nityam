import sys
from pathlib import Path

# Add the project root to sys.path so that shruti can be imported
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
