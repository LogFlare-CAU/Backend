import time
import jwt
import os

secret = os.getenv("JWT_SECRET", None)
algorithm = "HS256"
if not secret:
    raise Exception("JWT_SECRET environment variable is not set")

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
