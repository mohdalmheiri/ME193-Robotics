"""
Small, read-only check that the Onshape API keys work, run before a full export.

How it works:
  1. python-dotenv searches for a .env file starting in this script's folder (cad/)
     and moving up, so it finds "HW8 - Silly Walks Simulated/.env". It copies the
     three ONSHAPE_* lines into environment variables, which is where
     onshape-to-robot's client looks for them.
  2. We make the same Onshape client that onshape-to-robot uses for the export,
     with logging turned off so it never prints request headers (they are
     signed with the secret key).
  3. We ask Onshape for one thing only: the list of tabs ("elements") in the
     document. That call needs valid keys and access to the document. If it
     succeeds, the export can talk to Onshape too.
  4. We print each tab's name and type and check that "Part Studio 1" and
     "Assembly 1" are there. The key values are never printed.

Run from anywhere:   python "cad/test_connection.py"
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from onshape_to_robot.onshape_api.client import Client

# The document and workspace IDs come from the Onshape URL:
#   .../documents/<DOCUMENT_ID>/w/<WORKSPACE_ID>/e/<ELEMENT_ID>
DOCUMENT_ID = "c2d51f0d948908e24e9a3ad3"
WORKSPACE_ID = "05cb44dceb699dcff0cec69b"

# Load "../.env" (relative to this file) into environment variables.
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

# Fail early with a clear message (but no values) if a key is missing.
for name in ("ONSHAPE_API", "ONSHAPE_ACCESS_KEY", "ONSHAPE_SECRET_KEY"):
    if not os.getenv(name):
        sys.exit(f"{name} is empty or missing in {env_path}")

# The client insists on reading a JSON config file (an old way of storing keys).
# Our cad/config.json has no keys in it, so the client falls back to the
# environment variables loaded above, exactly as the real export does.
config_path = Path(__file__).resolve().parent / "config.json"
client = Client(stack=os.environ["ONSHAPE_API"], logging=False, creds=str(config_path))

try:
    elements = client.list_elements(DOCUMENT_ID, WORKSPACE_ID)
except Exception as exc:  # bad keys, no access, no internet...
    sys.exit(f"Connection FAILED: {type(exc).__name__}: {exc}")

if not isinstance(elements, list):
    # Onshape answers errors with a JSON object (e.g. {"message": "Unauthenticated"})
    sys.exit(f"Connection FAILED, Onshape replied: {elements}")

print("Connection OK. Tabs in the document:")
for el in elements:
    print(f"  - {el['name']!r:24} type={el['elementType']:12} id={el['id']}")

names = {el["name"] for el in elements}
for wanted in ("Part Studio 1", "Assembly 1"):
    print(f"{wanted!r}: {'found' if wanted in names else 'NOT FOUND'}")
