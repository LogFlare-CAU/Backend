from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2 해시 생성기 (메모리·시간·병렬성 조정 가능)
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

def hash_password(password: str) -> str:
    """비밀번호를 Argon2로 해시."""
    return ph.hash(password)

def verify_password(stored_password_hash: str, provided_password: str) -> bool:
    """입력된 비밀번호가 저장된 해시와 일치하는지 검증."""
    try:
        ph.verify(stored_password_hash, provided_password)
        return True
    except VerifyMismatchError:
        return False
