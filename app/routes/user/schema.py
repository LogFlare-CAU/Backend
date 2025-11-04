from common.schema import make_named_response
from .model import User


UserResponse = make_named_response(User, "UserResponse")