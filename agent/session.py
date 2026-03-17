from config.config import Config
from context.manager import ContextManager
from tools.registry import create_default_registry
from client.llm_client import LLMClient
import uuid
from datetime import datetime
from config.loader import get_data_dir
from tools.discovery import ToolDiscoveryManager

class Session:
    def __init__(self, config: Config):
        self.config = config
        self.tool_registry = create_default_registry(self.config)
        self.context_manager = ContextManager(
            config = self.config, 
            user_memory=self._load_memory(),
            tools=self.tool_registry.get_all_tools()
            )
        
        self.client = LLMClient(
            config = config
        )
        self.discovery_manager = ToolDiscoveryManager(config, self.tool_registry)
        self.discovery_manager.discover_all()
        self.session_id = str(uuid.uuid4())
        self.created_at = datetime.now()
        self.update_at = datetime.now()

        self._turn_count = 0

    def _load_memory(self) -> str | None:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "user_memory.json"

        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            entries = data.get('entries')
            if not entries:
                return None
            line = ["User prefences and notes:"]
            for key, value in sorted(entries.items()):
                line.append(f"- {key}: {value}")
            return "\n".join(line)
        except Exception:
            return None
    
    def increment_turn(self) -> int:
        self._turn_count += 1
        self.update_at = datetime.now()
        return self._turn_count

    
