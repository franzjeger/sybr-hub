"""Transport-independent authorization for state-changing actions."""

from app.core.exceptions import ForbiddenError
from app.models.user import Role, User


def require_write(user: User, min_role: Role = Role.technician, *, tenant: bool = False) -> None:
    if user.role < min_role or not user.can_write or (tenant and not user.tenant_write):
        raise ForbiddenError("Handlingen krever riktig rolle og eksplisitt skrivetilgang")
