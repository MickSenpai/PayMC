import os, sys, tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
