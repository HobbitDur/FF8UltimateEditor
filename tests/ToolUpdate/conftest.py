import pathlib
import sys

# Make the project root importable (ToolUpdate, Patcher) whatever the pytest invocation
project_root = pathlib.Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
