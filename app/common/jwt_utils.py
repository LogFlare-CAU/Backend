import time
import jwt

from .env_utils import getenvval

algorithm = "HS256"
secret = getenvval("JWT_SECRET")

def generate_jwt(payload: dict):
    """
    Generate a JSON Web Token (JWT) from the given payload.

    :param payload: Dictionary containing the payload data.
    :return: Encoded JWT as a string.
    """
    payload['iat'] = int(time.time())
    token = jwt.encode(payload, secret, algorithm=algorithm)
    return token

def decode_jwt(payload:str):
    return jwt.decode(payload, secret, algorithms=[algorithm])
