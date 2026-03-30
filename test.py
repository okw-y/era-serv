import os
import time
import hashlib


CUSTOM_EPOCH = 1704067200000
SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000


def generate_msg_id(room_pub_key: str, timestamp_ms: int) -> int:
    time_part = (timestamp_ms - CUSTOM_EPOCH) & 0x1FFFFFFFFFF

    room_hash = int(hashlib.sha256(room_pub_key.encode()).hexdigest()[:4], 16) & 0x3FF
    rand_part = int.from_bytes(os.urandom(2), byteorder='big') & 0xFFF

    msg_id = (time_part << 22) | (room_hash << 12) | rand_part
    return msg_id


def analyze_msg_id(msg_id: int) -> dict:
    current_time_ms = int(time.time() * 1000)

    time_part = (msg_id >> 22) & 0x1FFFFFFFFFF
    created_timestamp_ms = time_part + CUSTOM_EPOCH

    parent_identifier = (msg_id >> 12) & 0x3FF

    age_ms = current_time_ms - created_timestamp_ms
    is_relevant = 0 <= age_ms <= SEVEN_DAYS_MS

    return {
        "created_timestamp_ms": created_timestamp_ms,  # Временное значение создания
        "parent_identifier": parent_identifier,  # Родительский идентификатор
        "is_relevant": is_relevant,  # Релевантно или подлежит удалению
        "age_days": round(age_ms / (1000 * 60 * 60 * 24), 2)  # Возраст в днях
    }



now = int(time.time())
output = []
for i in range(now, now + 10000):
    output.append(generate_msg_id("11498917-18b4-41b1-8466-79296d11d425", i))

print(*output, sep="\n")

print("\n\n")
print(output == sorted(output))
