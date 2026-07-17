import logging

FMT = "%(asctime)s:%(levelname)s:%(name)s:%(message)s"
CONSOLE_FMT = "%(levelname)s:%(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name="logflare") -> logging.Logger:
    logger = logging.getLogger("logflare")
    if not getattr(logger, "_logflare_configured", False):
        formatter = logging.Formatter(FMT, DATEFMT)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logger._logflare_configured = True

    return logger


def setup_uvicorn_file_logging() -> None:
    # ← 여기서 관련 로거들을 모두 포함
    target_names = (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "logflare",  # 프로젝트 공통 로거
    )
    targets = [logging.getLogger(n) for n in target_names]

    console_formatter = logging.Formatter(CONSOLE_FMT)

    # info_handler = RotatingFileHandler(infofile, mode="w", encoding="utf-8")
    # info_handler.setLevel(logging.INFO)
    # info_handler.setFormatter(formatter)
    #
    # error_handler = RotatingFileHandler(errorfile, mode="a", encoding="utf-8")
    # error_handler.setLevel(logging.ERROR)
    # error_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    for lg in targets:
        if not getattr(lg, "_logflare_configured", False):
            # uvicorn이 붙여놓은 기본 콘솔 핸들러 제거(중복 방지)
            for h in list(lg.handlers):
                lg.removeHandler(h)

            # lg.addHandler(info_handler)
            # lg.addHandler(error_handler)
            lg.addHandler(console_handler)

            lg.propagate = False
            lg.setLevel(logging.INFO)
            lg._logflare_configured = True
