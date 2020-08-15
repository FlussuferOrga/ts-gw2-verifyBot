from typing import Tuple

from flask import Response, jsonify


def error_response(code: int = 500, name: str = None, desc: str = None) -> Tuple[Response, int]:
    return jsonify(code=code, name=name, desc=desc), code
