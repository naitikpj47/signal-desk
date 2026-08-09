# Runs before any test module imports app code:
#  - guarantees backend/ is importable (pytest adds this dir to sys.path)
#  - points the app at a throwaway database so tests never touch signaldesk.db
import os
import tempfile

_TEST_DB = os.path.join(tempfile.gettempdir(), "signaldesk_test.db")
os.environ["SIGNALDESK_DB"] = _TEST_DB
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
