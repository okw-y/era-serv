import hashlib


def generate_msg_id(room_pub_key: str, timestamp: int) -> int:
    hash_obj = hashlib.sha256(
        f"{room_pub_key}{timestamp}".encode()
    ).hexdigest()

    return int(hash_obj, 16) % (2 ** 63 - 1)\
