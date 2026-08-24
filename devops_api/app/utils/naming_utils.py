from datetime import datetime
import uuid

def generate_filename(prefix: str, user_id: int, session_id: int = None, extension: str = "yml") -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    short_uuid = str(uuid.uuid4())[:6]
    parts = [prefix, f"user{user_id}"]
    if session_id:
        parts.append(str(session_id))
    parts.append(timestamp)
    parts.append(short_uuid)
    return "_".join(parts) + f".{extension}"
