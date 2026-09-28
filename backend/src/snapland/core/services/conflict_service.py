from typing import Sequence
from snapland.core.domain.area import Area

class ConflictError(Exception):
    def __init__(self, current_area: Area) -> None:
        super().__init__("Area was modified by another user")
        self.current_area = current_area
