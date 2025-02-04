from queue import Queue
import threading
from amazon_scraper import AmazonScraper
from logger import setup_logger
from concurrent.futures import ThreadPoolExecutor
from utils import load_config
import time
import json
import os
from pathlib import Path

class SessionPool:
    def __init__(self, pool_size=30):
        self.logger = setup_logger('SessionPool')
        self.pool_size = pool_size
        self.sessions = Queue()
        self.lock = threading.Lock()
        self.config = load_config()
        self.cache_file = Path("cached_sessions.json")
        
    def _save_sessions_to_cache(self):
        """Save session data to cache file"""
        try:
            # Get all sessions from queue temporarily
            sessions = []
            session_data = []
            while not self.sessions.empty():
                session = self.sessions.get()
                sessions.append(session)
                
                # Extract essential session data
                session_data.append({
                    'cookies': dict(session.session.cookies.items()),
                    'proxy': session.proxy,
                    'csrf_token': session.initial_csrf_token
                })
            
            # Put sessions back in queue
            for session in sessions:
                self.sessions.put(session)
            
            # Save to file
            with open(self.cache_file, 'w') as f:
                json.dump(session_data, f)
                
            self.logger.info(f"Saved {len(session_data)} sessions to cache")
            
        except Exception as e:
            self.logger.error(f"Failed to save sessions to cache: {str(e)}")
    
    def _load_sessions_from_cache(self):
        """Try to load sessions from cache file"""
        if not self.cache_file.exists():
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                session_data = json.load(f)
            
            self.logger.info(f"Found {len(session_data)} cached sessions")
            
            max_concurrent = self.config.get('max_concurrent_zipcode_scrapers', 40)
            self.logger.info(f"Loading cached sessions with {max_concurrent} concurrent workers")
            
            def load_single_session(data):
                try:
                    scraper = AmazonScraper()
                    scraper._create_fresh_session()
                    
                    # Restore session data
                    for cookie_name, cookie_value in data['cookies'].items():
                        scraper.session.cookies.set(cookie_name, cookie_value)
                    scraper.proxy = data['proxy']
                    scraper.initial_csrf_token = data['csrf_token']
                    scraper.is_initialized = True
                    
                    # Verify session is still valid by making a test request
                    if scraper._make_modal_html_request(scraper.initial_csrf_token):
                        return scraper
                    else:
                        self.logger.warning("Cached session validation failed")
                        return None
                        
                except Exception as e:
                    self.logger.error(f"Failed to restore cached session: {str(e)}")
                    return None
            
            successful = 0
            with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                # Submit all cached sessions for loading
                futures = []
                for data in session_data[:self.pool_size]:
                    futures.append(executor.submit(load_single_session, data))
                
                # Process results as they complete
                for future in futures:
                    try:
                        scraper = future.result()
                        if scraper:
                            self.sessions.put(scraper)
                            successful += 1
                    except Exception as e:
                        self.logger.error(f"Error loading cached session: {str(e)}")
            
            self.logger.info(f"Successfully restored {successful} sessions from cache")
            return successful > 0
            
        except Exception as e:
            self.logger.error(f"Failed to load sessions from cache: {str(e)}")
            return False
        
    def initialize_pool(self):
        """Initialize the pool with sessions concurrently"""
        start_time = time.time()
        
        # Try to load from cache first
        if self._load_sessions_from_cache():
            remaining = self.pool_size - self.sessions.qsize()
            cache_time = time.time() - start_time
            self.logger.info(f"Cache loading took {cache_time:.2f} seconds")
            
            if remaining <= 0:
                self.logger.info(f"Pool fully initialized from cache in {cache_time:.2f} seconds")
                return
            self.logger.info(f"Initializing remaining {remaining} sessions...")
            self.pool_size = remaining
            start_time = time.time()  # Reset timer for remaining sessions
        else:
            self.logger.info(f"Initializing fresh pool with {self.pool_size} sessions...")
        
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
        
        init_time = time.time() - start_time
        total_time = time.time() - start_time
        self.logger.info(
            f"Pool initialization completed in {total_time:.2f} seconds. "
            f"Successfully initialized {self.sessions.qsize()}/{self.pool_size} sessions "
            f"({completed} successful, {failed} failed)"
        )
        
        # Save newly initialized sessions to cache
        cache_start = time.time()
        self._save_sessions_to_cache()
        cache_time = time.time() - cache_start
        self.logger.info(f"Session caching took {cache_time:.2f} seconds")
    
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