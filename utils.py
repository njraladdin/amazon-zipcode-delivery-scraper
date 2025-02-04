import json
import os
from pathlib import Path
from dotenv import load_dotenv
from logger import setup_logger

logger = setup_logger('Utils')

def load_config():
    """
    Load configuration based on environment setting from .env file
    """
    # Load environment variables from .env file
    load_dotenv()
    
    # Get environment, default to production if not set
    env = os.getenv('ENVIRONMENT', 'production').lower()
    
    config_path = Path(__file__).parent / f"config.{env}.json"
    
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
            logger.info(f"Loaded configuration for {env} environment")
            return config
    except Exception as e:
        logger.error(f"Error loading config.{env}.json: {e}")
        return {
            "max_concurrent_zipcode_scrapers": 50,
            "port": 8080,
            "allow_proxy": True
        } 