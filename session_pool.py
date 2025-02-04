from queue import Queue
import threading
from amazon_scraper import AmazonScraper
from logger import setup_logger
from concurrent.futures import ThreadPoolExecutor
from utils import load_config
import time

class SessionPool:
    def __init__(self, pool_size=30):
        self.logger = setup_logger('SessionPool')
        self.pool_size = pool_size
        self.sessions = Queue()
        self.lock = threading.Lock()
        self.config = load_config()
        
    def initialize_pool(self):
        """Initialize the pool with sessions concurrently"""
        self.logger.info(f"Initializing pool with {self.pool_size} sessions...")
        
        max_concurrent = self.config.get('max_concurrent_zipcode_scrapers', 40)
        self.logger.info(f"Using max concurrent initializations: {max_concurrent}")
        
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # Submit all initialization tasks
            futures = []
            for i in range(self.pool_size):
                future = executor.submit(self._initialize_single_session, i)
                futures.append(future)
            
            # Track progress
            completed = 0
            failed = 0
            for future in futures:
                try:
                    if future.result():
                        completed += 1
                    else:
                        failed += 1
                except Exception as e:
                    self.logger.error(f"Session initialization failed with error: {str(e)}")
                    failed += 1
                
                # Log progress
                total = completed + failed
                self.logger.info(f"Progress: {total}/{self.pool_size} "
                               f"(Success: {completed}, Failed: {failed})")
        
        self.logger.info(f"Pool initialization completed. "
                        f"Successfully initialized {self.sessions.qsize()}/{self.pool_size} sessions")
    
    def _initialize_single_session(self, index):
        """Initialize a single session"""
        try:
            scraper = AmazonScraper()
            if scraper.initialize_session():
                self.sessions.put(scraper)
                self.logger.info(f"Successfully initialized session {index + 1}")
                return True
            else:
                self.logger.error(f"Failed to initialize session {index + 1}")
                return False
        except Exception as e:
            self.logger.error(f"Error initializing session {index + 1}: {str(e)}")
            return False
    
    def get_session(self):
        """Get a session from the pool"""
        return self.sessions.get()
    
    def return_session(self, session):
        """Return a session to the pool"""
        self.sessions.put(session)
    
    def get_pool_size(self):
        """Get current number of available sessions"""
        return self.sessions.qsize() 