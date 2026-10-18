from datetime import UTC, datetime


def utc_iso(dt: datetime) -> str:
    """naive 는 UTC 로 간주, aware 는 UTC 로 변환해 오프셋이 붙은 ISO 문자열로."""
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.isoformat()


def utc_dict(obj) -> dict:
    """dict(obj) 에서 datetime 컬럼만 utc_iso 로 바꾼다 (Base 직렬화는 오프셋을 버린다)."""
    return {
        k: utc_iso(getattr(obj, k)) if isinstance(getattr(obj, k, None), datetime) else v
        for k, v in dict(obj).items()
    }
