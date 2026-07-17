from sqlalchemy import case

from routes.logs.enum import Level

LEVEL_ORDER = [
    Level.DEBUG,
    Level.INFO,
    Level.WARNING,
    Level.ERROR,
    Level.CRITICAL,
]

def level_order_expr(level_field):
    # SQLAlchemy 2.x 문법: dict를 첫 인자로 넣고 value= 로 매칭
    order_map = {lvl.value: idx for idx, lvl in enumerate(LEVEL_ORDER, start=1)}
    return case(
        order_map,       # ← old whens= 대신 dict 자체를 positional argument로 넣음
        value=level_field,
        else_=0
    )

def get_sort_order(sort: str, timestamp_field, level_field):
    level_expr = level_order_expr(level_field)

    match sort:
        case "newest":
            return timestamp_field.desc()
        case "oldest":
            return timestamp_field.asc()
        case "highest":
            return level_expr.desc()
        case "lowest":
            return level_expr.asc()
        case _:
            return timestamp_field.desc()
