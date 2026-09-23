"""The reviewed administrative surface, shared by server and agent clients."""
from dataclasses import dataclass
from importlib.resources import files
import json


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    path: str
    operation_id: str
    summary: str
    read_only_override: bool | None = None

    @property
    def read_only(self) -> bool:
        return self.method == "GET" if self.read_only_override is None else self.read_only_override


OPERATIONS = tuple(Operation(**entry) for entry in json.loads(
    files("litellm_admin_mcp").joinpath("operations.json").read_text()
))
BY_NAME = {operation.name: operation for operation in OPERATIONS}
