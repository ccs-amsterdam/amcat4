import base64
import json
import os
import secrets
import time
from typing import Dict, Optional

import httpx
from jose import jwt


def decode_claims(token: str) -> Dict:
    _, payload, _ = token.split(".")
    decoded = base64.urlsafe_b64decode(payload + "==").decode("utf-8")
    return json.loads(decoded)
