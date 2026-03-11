from pydantic import BaseModel, Field
from pathlib import Path
import os

class ModelConfig(BaseModel):
    name: str = "stepfun/step-3.5-flash:free"
    temperature: float = Field(default=1, ge=0.0, le=2.0)
    context_window: int = 256000
    
    

class Config(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    cwd: Path = Field(default_factory=Path.cwd)

    max_turns: int = 100

    developer_instructions: str | None = None
    user_instructions: str | None = None 

    debug: bool = False

    @property
    def api_key(self) -> str | None:
        return os.environ.get("API_KEY")
    
    @property
    def base_url(self) -> str | None:
        return os.environ.get("BASE_URL")

    @property
    def model_name(self) -> str:
        return self.model.name
    
    @model_name.setter
    def model_name(self , value: str ) -> None:
        self.model.name = value

    @property
    def temperature(self, value: str ) -> None:
        self.model.temperature = value
    
    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.api_key:
            errors.append("No API key found in the environement variable")
        if not self.cwd.exists():
            errors.append(f"Working directory does not exists: {self.cwd}")
        
        return errors