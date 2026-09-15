from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantId:
    value: UUID

    @classmethod
    def from_string(cls, value: str) -> "TenantId":
        return cls(UUID(value))

    def __str__(self) -> str:
        return str(self.value)
