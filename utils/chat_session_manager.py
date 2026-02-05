import os
import json
import logging
from langchain_core.messages import messages_to_dict, messages_from_dict
from utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

class ChatSessionManager:
    """
    Manages chat session persistence, switching between Redis and Memory.
    """
    def __init__(self, session_type="chat_session"):
        self.memory_store = {}
        self.session_type = session_type
        self.redis_prefix = os.getenv("REDIS_PREFIX", "langextract")
        # Check specific feature flag first, then general enabled flag
        self.redis_enabled = (os.getenv("REDIS_CHAT_SESSION_ENABLED", "0") == "1") and \
                             (os.getenv("REDIS_ENABLED", "0") == "1")
        self.ttl = 24 * 60 * 60 * 7 # 7 days
        self.env = os.getenv("ENV", "dev")
        
        if self.redis_enabled:
            logger.info(f"🚀 ChatSessionManager ({self.session_type}): Redis persistence ENABLED")
        else:
            logger.info(f"⚠️ ChatSessionManager ({self.session_type}): Using In-Memory Store")

    def _get_key(self, task_id):
        return f"{self.redis_prefix}:{self.env}:{self.session_type}:{task_id}"

    def _get_redis(self):
        try:
            client = get_redis_client()
            if client:
                return client
        except Exception as e:
            logger.error(f"Failed to get Redis client: {e}")
        return None

    def get_session(self, task_id):
        if self.redis_enabled:
            client = self._get_redis()
            if client:
                try:
                    key = self._get_key(task_id)
                    data = client.get(key)
                    if data:
                        messages_dict = json.loads(data)
                        return messages_from_dict(messages_dict)
                except Exception as e:
                    logger.error(f"Redis get session failed: {e}")
        
        return self.memory_store.get(task_id, [])

    def update_session(self, task_id, messages):
        if self.redis_enabled:
            client = self._get_redis()
            if client:
                try:
                    key = self._get_key(task_id)
                    # Serialize
                    messages_dict = messages_to_dict(messages)
                    # Ensure Chinese characters are not escaped in JSON for readability (optional but good for debugging)
                    client.setex(key, self.ttl, json.dumps(messages_dict, ensure_ascii=False))
                    return
                except Exception as e:
                    logger.error(f"Redis set session failed: {e}")
        
        self.memory_store[task_id] = messages
