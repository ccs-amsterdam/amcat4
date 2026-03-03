import base64
import json
from typing import Dict


def decode_claims(token: str) -> Dict:
    _, payload, _ = token.split(".")
    decoded = base64.urlsafe_b64decode(payload + "==").decode("utf-8")
    return json.loads(decoded)
