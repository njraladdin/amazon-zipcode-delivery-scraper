from queue import Queue, Empty
import threading
from amazon_scraper import AmazonScraper
from logger import setup_logger
from concurrent.futures import ThreadPoolExecutor
from utils import load_config
import time
import json
import os
from pathlib import Path

ALLOW_HEALTH_AND_FACTORY_CHECKS = True

class SessionPool:
    def __init__(self):
        self.logger = setup_logger('SessionPool')
        self.config = load_config()
        # Use config values with fallbacks
        self.min_available_sessions_in_reserve = self.config.get('initial_session_pool_size', 200)  # Use 200 as fallback
        self.refill_threshold = self.config.get('session_pool_refill_threshold', 100)  # Use 100 as fallback
        self.sessions = Queue()
        self.lock = threading.Lock()
        self.cache_file = Path("cached_sessions.json")
        self.is_refilling = False  # New flag to track refill state
        self.discarded_sessions_count = 0  # Add counter for discarded sessions
        
        # Log the initialization values
        self.logger.info(f"Initializing SessionPool with: target_size={self.min_available_sessions_in_reserve}, "
                        f"refill_threshold={self.refill_threshold}")
        
        # Initialize factory thread but don't start it yet
        self.should_run = False
        self.factory_thread = None
        self.health_check_thread = None  # New thread for health checks
        
    def start_background_factory(self):
        """Start the background factory thread if needed"""
        if not ALLOW_HEALTH_AND_FACTORY_CHECKS:
            self.logger.info("Background factory disabled by configuration")
            return
            
        with self.lock:
            if not self.factory_thread or not self.factory_thread.is_alive():
                self.should_run = True
                self.factory_thread = threading.Thread(target=self._session_factory_worker, daemon=True)
                self.factory_thread.start()
                self.logger.info("Started background session factory")
            else:
                self.logger.info("Factory thread already running")
        
    def _session_factory_worker(self):
        """Background worker that maintains minimum session count with limited concurrency"""
        FACTORY_MAX_CONCURRENT = 10  # Limited concurrent session creations. TODO : make this dynamic, if the reserve is too low then increase concurrency limit 
        FACTORY_CHECK_INTERVAL = 5   # Seconds between checks
        
        while self.should_run:
            try:
                current_size = self.sessions.qsize()
                
                # Add info logging
                self.logger.info(f"Factory check - Current pool size: {current_size}, " 
                                f"Threshold: {self.refill_threshold}, "
                                f"Is refilling: {self.is_refilling}")
                
                # Start refilling if below threshold or continue if already refilling
                if current_size < self.refill_threshold or self.is_refilling:
                    self.is_refilling = True
                    sessions_needed = self.min_available_sessions_in_reserve - current_size
                    
                    self.logger.info(f"Checking refill conditions: current_size={current_size}, "
                                   f"refill_threshold={self.refill_threshold}, "
                                   f"min_reserve={self.min_available_sessions_in_reserve}, "
                                   f"sessions_needed={sessions_needed}")
                    
                    if sessions_needed <= 0:
                        # We've reached the full reserve size
                        self.is_refilling = False
                        self.logger.info("Factory reached target pool size, pausing refill")
                        time.sleep(FACTORY_CHECK_INTERVAL)
                        continue
                        
                    self.logger.info(f"Factory starting to create {sessions_needed} new sessions. "
                                   f"Current pool size: {current_size}")
                    
                    # Create sessions with limited concurrency
                    with ThreadPoolExecutor(max_workers=FACTORY_MAX_CONCURRENT) as executor:
                        batch_size = min(FACTORY_MAX_CONCURRENT, sessions_needed)
                        self.logger.info(f"Creating batch of {batch_size} sessions")
                        
                        futures = [executor.submit(self._initialize_single_session, i) 
                                 for i in range(batch_size)]
                        
                        successful = 0
                        for future in futures:
                            try:
                                if future.result():
                                    successful += 1
                            except Exception as e:
                                self.logger.error(f"Factory failed to create session: {str(e)}")
                        
                        self.logger.info(f"Batch complete - Created {successful}/{batch_size} sessions")
                
                time.sleep(FACTORY_CHECK_INTERVAL)
                
            except Exception as e:
                self.logger.error(f"Error in session factory: {str(e)}")
                time.sleep(FACTORY_CHECK_INTERVAL * 2)  # Double interval on error
    
    def start_health_checker(self):
        """Start the background health check thread if needed"""
        if not ALLOW_HEALTH_AND_FACTORY_CHECKS:
            self.logger.info("Health checker disabled by configuration")
            return
            
        with self.lock:
            if not self.health_check_thread or not self.health_check_thread.is_alive():
                self.should_run = True
                self.health_check_thread = threading.Thread(target=self._session_health_checker, daemon=True)
                self.health_check_thread.start()
                self.logger.info("Started background health checker")
            else:
                self.logger.info("Health checker thread already running")
    
    def _session_health_checker(self):
        """Background worker that checks sessions and maintains pool size limit"""
        CHECK_DELAY = 20  # Small delay between session checks
        
        while self.should_run:
            try:
                # Get a snapshot of current sessions without removing them
                with self.lock:
                    current_size = self.sessions.qsize()
                    sessions_snapshot = list(self.sessions.queue)  # Get internal queue list
                    max_size = self.config.get("max_sessions_in_pool", 500)
                    
                    # If over max size, remove excess sessions
                    if current_size > max_size:
                        excess = current_size - max_size
                        self.logger.info(f"Pool over max size ({current_size}/{max_size}). Removing {excess} sessions")
                        for _ in range(excess):
                            try:
                                self.sessions.get_nowait()
                                self.discarded_sessions_count += 1
                            except Empty:
                                break
                
                self.logger.debug(f"Starting health check cycle of {len(sessions_snapshot)} sessions")
                
                # Check each session
                for session in sessions_snapshot:
                    if session and session.is_initialized:
                        is_healthy = session._make_modal_html_request(session.initial_csrf_token)
                        if not is_healthy:
                            # Only remove unhealthy sessions
                            with self.lock:
                                try:
                                    self.sessions.queue.remove(session)
                                    self.discarded_sessions_count += 1
                                    self.logger.warning("Removed unhealthy session from pool")
                                except ValueError:
                                    pass  # Session was already removed
                
                    time.sleep(CHECK_DELAY)  # Small delay between each session check
                
                self.logger.info(f"Health check cycle complete - {self.discarded_sessions_count} sessions discarded")
                time.sleep(60)

            except Exception as e:
                self.logger.error(f"Error in health checker: {str(e)}")
                time.sleep(5)  # Short sleep on error before retrying
    
    def shutdown(self):
        """Cleanup method to stop all background threads"""
        self.should_run = False
        if self.factory_thread:
            self.factory_thread.join()
        if self.health_check_thread:
            self.health_check_thread.join()
    
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
        
        # Check cache age
        cache_age = time.time() - self.cache_file.stat().st_mtime
        if cache_age > 86400:  # 86400 seconds = 24 hours
            self.logger.info(f"Cache file is {cache_age/3600:.1f} hours old. Deleting old cache.")
            self.cache_file.unlink()  # Delete the old cache file
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
                for data in session_data[:self.min_available_sessions_in_reserve]:
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
        """Initialize the pool with sessions concurrently. Returns number of successful sessions created."""
        start_time = time.time()
        successful_sessions = 0
        
        # Try to load from cache first
        if self._load_sessions_from_cache():
            successful_sessions = self.sessions.qsize()
            remaining = self.min_available_sessions_in_reserve - successful_sessions
            cache_time = time.time() - start_time
            self.logger.info(f"Cache loading took {cache_time:.2f} seconds")
            
            if remaining <= 0:
                self.logger.info(f"Pool fully initialized from cache in {cache_time:.2f} seconds")
                return successful_sessions
            
            self.logger.info(f"Initializing remaining {remaining} sessions...")
            target_sessions = remaining
            start_time = time.time()  # Reset timer for remaining sessions
        else:
            self.logger.info(f"Initializing fresh pool with {self.min_available_sessions_in_reserve} sessions...")
            target_sessions = self.min_available_sessions_in_reserve
        
        max_concurrent = self.config.get('max_concurrent_zipcode_scrapers', 40)
        self.logger.info(f"Using max concurrent initializations: {max_concurrent}")
        
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = []
            for i in range(target_sessions):
                future = executor.submit(self._initialize_single_session, i)
                futures.append(future)
            
            # Track progress and check error rate
            completed = 0
            failed = 0
            error_threshold = min(5, target_sessions // 2)  # 50% of target or at least 5 errors
            min_success_rate = 0.2  # At least 20% success rate
            
            for future in futures:
                try:
                    if future.result():
                        completed += 1
                        successful_sessions += 1
                    else:
                        failed += 1
                except Exception as e:
                    self.logger.error(f"Session initialization failed with error: {str(e)}")
                    failed += 1
                
                # Check if we should abort due to too many errors
                if failed >= error_threshold:
                    current_success_rate = completed / (completed + failed)
                    if current_success_rate < min_success_rate:
                        self.logger.error(
                            f"Aborting pool initialization: Too many errors "
                            f"({failed} errors, {completed} successes, {current_success_rate:.1%} success rate)"
                        )
                        # Return current successful sessions - main.py will decide if it's enough
                        return successful_sessions
                
                # Log progress
                total = completed + failed
                self.logger.info(f"Progress: {total}/{target_sessions} "
                               f"(Success: {completed}, Failed: {failed})")
        
        total_time = time.time() - start_time
        self.logger.info(
            f"Pool initialization completed in {total_time:.2f} seconds. "
            f"Successfully initialized {successful_sessions}/{self.min_available_sessions_in_reserve} sessions "
            f"({completed} successful, {failed} failed)"
        )
        
        # Save newly initialized sessions to cache
        cache_start = time.time()
        self._save_sessions_to_cache()
        cache_time = time.time() - cache_start
        self.logger.info(f"Session caching took {cache_time:.2f} seconds")
        
        return successful_sessions
    
    def _initialize_single_session(self, index):
        """Initialize a single session with retry mechanism"""
        max_retries = 2
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                scraper = AmazonScraper()
                if scraper.initialize_session():
                    self.sessions.put(scraper)
                    self.logger.info(f"Successfully initialized session {index + 1} on attempt {retry_count + 1}")
                    return True
                else:
                    retry_count += 1
                    if retry_count < max_retries:
                        self.logger.warning(f"Failed to initialize session {index + 1}, attempt {retry_count}/{max_retries}. Retrying...")
                    else:
                        self.logger.error(f"Failed to initialize session {index + 1} after {max_retries} attempts")
                        return False
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    self.logger.warning(f"Error initializing session {index + 1} on attempt {retry_count}/{max_retries}: {str(e)}. Retrying...")
                else:
                    self.logger.error(f"Error initializing session {index + 1} after {max_retries} attempts: {str(e)}")
                    return False
        
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

    def wait_for_sessions(self, needed_sessions, timeout=300):
        """Wait until enough sessions are available"""
        start_time = time.time()
        check_interval = 0.5  # Check every 0.5 seconds
        
        while (time.time() - start_time) < timeout:
            current_size = self.sessions.qsize()
            if current_size >= needed_sessions:
                return True
            
            self.logger.info(f"Waiting for sessions... Need {needed_sessions}, have {current_size}")
            time.sleep(check_interval)
            
        self.logger.error(f"Timeout waiting for {needed_sessions} sessions after {timeout} seconds")
        return False

    def get_sessions(self, count):
        """Get requested sessions, creating new ones if needed"""
        sessions = []
        current_size = self.sessions.qsize()
        
        # Try to get available sessions from pool first
        while not self.sessions.empty() and len(sessions) < count:
            try:
                sessions.append(self.sessions.get_nowait())
            except Empty:
                break
        
        # If we need more sessions, create them
        remaining = count - len(sessions)
        if remaining > 0:
            self.logger.info(f"Creating {remaining} new sessions on demand")
            
            error_count = 0
            success_count = 0
            
            with ThreadPoolExecutor(max_workers=min(remaining, 20)) as executor:
                futures = [
                    executor.submit(self._initialize_single_session, i) 
                    for i in range(remaining)
                ]
                
                # Define thresholds
                error_threshold = min(5, remaining // 2)  # 50% of remaining or at least 5 errors
                min_success_rate = 0.2  # At least 20% success rate
                
                for future in futures:
                    try:
                        result = future.result()
                        if result:
                            sessions.append(result)
                            success_count += 1
                        else:
                            error_count += 1
                    except Exception as e:
                        self.logger.error(f"Failed to create new session: {str(e)}")
                        error_count += 1
                    
                    # Check if we should abort due to too many errors
                    if error_count >= error_threshold:
                        success_rate = success_count / (success_count + error_count)
                        if success_rate < min_success_rate:
                            self.logger.error(f"Aborting session creation: Too many errors ({error_count} errors, "
                                            f"{success_count} successes, {success_rate:.1%} success rate)")
                            raise Exception(f"Too many errors creating new sessions. Success rate: {success_rate:.1%}")
        
        if len(sessions) < count:
            # If we still couldn't get enough sessions, raise error
            raise Exception(f"Could not create enough sessions. Requested: {count}, Created: {len(sessions)}")
        
        return sessions

    def return_sessions(self, sessions):
        """Return all valid sessions to pool"""
        valid_sessions = [s for s in sessions if s and s.is_initialized]
        
        self.logger.info(f"Returning {len(valid_sessions)} sessions to pool. Current size: {self.sessions.qsize()}")
        
        for session in valid_sessions:
            self.sessions.put(session)

    def start_background_workers(self):
        """Start both background factory and health check threads"""
        self.start_background_factory()
        self.start_health_checker()

def test_session_pool():
    """Test function to initialize a single session"""
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    pool = SessionPool()
    
    print("\n=== Initializing Single Session ===")
    success = pool._initialize_single_session(0)
    print(f"Session initialization {'successful' if success else 'failed'}")
    print(f"Current pool size: {pool.get_pool_size()}")
    
    pool.shutdown()
    print("\n=== Test completed ===")

if __name__ == "__main__":
    test_session_pool() 