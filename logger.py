import logging
from logging import StreamHandler, FileHandler
import sys
from colorama import init, Fore, Style
from datetime import datetime
import os
from pathlib import Path

# Initialize colorama
init(autoreset=True)

# Create logs directory if it doesn't exist
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels"""
    
    COLORS = {
        'DEBUG': Fore.BLUE,
        'INFO': Fore.CYAN,
        'SUCCESS': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT
    }

    def format(self, record):
        # Add custom SUCCESS level color if used
        if not hasattr(logging, 'SUCCESS'):
            logging.SUCCESS = 25  # Between INFO and WARNING
            logging.addLevelName(logging.SUCCESS, 'SUCCESS')
        
        # Only color the output if it's going to the console
        if isinstance(self._style._fmt, str) and '%(color_on)s' in self._style._fmt:
            record.color_on = self.COLORS.get(record.levelname, '')
            record.color_off = Style.RESET_ALL
        else:
            record.color_on = ''
            record.color_off = ''
        return super().format(record)

def setup_logger(name='AmazonScraper'):
    """Set up and return a colored logger instance"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Only add handlers if they don't exist
    if not logger.handlers:
        # Console handler with colors
        console_handler = StreamHandler(sys.stdout)
        colored_formatter = ColoredFormatter(
            fmt='%(color_on)s%(asctime)s.%(msecs)03d [%(thread)d] %(levelname)s: %(message)s%(color_off)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(colored_formatter)
        logger.addHandler(console_handler)
        
        # File handler without colors
        today = datetime.now().strftime('%Y-%m-%d')
        log_file = LOGS_DIR / f"{name}_{today}.log"
        file_handler = FileHandler(log_file, encoding='utf-8')
        file_formatter = logging.Formatter(
            fmt='%(asctime)s.%(msecs)03d [%(thread)d] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Add success method to logger
    def success(self, message, *args, **kwargs):
        self.log(logging.SUCCESS, message, *args, **kwargs)
    
    logger.success = success.__get__(logger)
    return logger 