from enum import Enum

class State(Enum):
    GREETING = 1
    ASK_DESTINATION = 2
    ASK_START = 3
    ASK_TIME = 4
    SHOW_ROUTE = 5
    END = 6
