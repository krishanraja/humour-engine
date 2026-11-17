from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    """Base for every contract: unknown fields are errors, assignment is validated."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, frozen=False)
