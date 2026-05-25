from dotenv import load_dotenv
import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

uri = os.environ["MONGODB_URI"]
client = MongoClient(uri, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    print("[OK] MongoDB - connected to Atlas")
except Exception as e:
    print(f"[FAIL] MongoDB - {e}")
