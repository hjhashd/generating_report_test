import os
import redis
import logging

# Configure logging
logger = logging.getLogger(__name__)

class RedisClient:
    _instance = None
    _pool = None
    
    @classmethod
    def get_client(cls):
        """
        Get a Redis client instance.
        Returns None if REDIS_ENABLED is not '1' or if connection fails.
        """
        if os.getenv("REDIS_ENABLED", "0") != "1":
            return None

        if cls._instance is None:
            try:
                cls._instance = cls._create_client()
            except Exception as e:
                logger.error(f"Failed to initialize Redis client: {e}")
                return None
        return cls._instance

    @classmethod
    def _create_client(cls):
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", 6379))
        password = os.getenv("REDIS_PASSWORD", "")
        db = int(os.getenv("REDIS_DB", 0))
        
        # Use ConnectionPool for better performance
        if cls._pool is None:
            cls._pool = redis.ConnectionPool(
                host=host,
                port=port,
                password=password,
                db=db,
                decode_responses=True, # Return strings
                socket_timeout=2,
                socket_connect_timeout=2,
                retry_on_timeout=True
            )
        
        client = redis.Redis(connection_pool=cls._pool)
        
        # Quick health check
        try:
            client.ping()
            logger.info(f"Redis connected successfully to {host}:{port}/{db}")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection ping failed: {e}")
            # We return the client anyway, as it might recover, 
            # but usually we might want to return None if strictly unavailable.
            # For now, let's return None to trigger fallback logic immediately if down.
            return None
            
        return client

def get_redis_client():
    return RedisClient.get_client()
