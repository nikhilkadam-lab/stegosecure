import hashlib

def normalize_answer(answer: str) -> str:
    return answer.strip().lower()

def sha256_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
