from snapland.core.domain.area import Area

class SnaplandError(Exception):
    pass

class AuthError(SnaplandError):
    pass

class NotFoundError(SnaplandError):
    pass

class ForbiddenError(SnaplandError):
    pass

class ConflictError(SnaplandError):
    def __init__(self, current_area: Area) -> None:
        super().__init__("Area was modified by another user")
        self.current_area = current_area
