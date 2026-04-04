import time
import threading
import requests

try:
    from app.main import app
    print("IMPORT SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
    print("IMPORT ERROR")
    exit(1)
