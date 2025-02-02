import json
from pathlib import Path
from logger import setup_logger

logger = setup_logger('Utils')

def load_config():
    """
    Load configuration from config.json file.
    Returns a dictionary with configuration values.
    """
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config.json: {e}")
        return {
            "max_concurrent_zipcode_scrapers": 50,
            "port": 8080,
            "allow_proxy": True
        } 