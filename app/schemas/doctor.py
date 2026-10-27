from pydantic import BaseModel, ConfigDict


class DoctorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    specialty: str
    is_active: bool
