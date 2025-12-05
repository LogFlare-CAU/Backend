from enum import Enum

class Sort(Enum):
    NEWEST = 'newest'
    OLDEST = 'oldest'
    HIGHEST= 'highest'
    LOWEST = 'lowest'

class Level(Enum):
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'