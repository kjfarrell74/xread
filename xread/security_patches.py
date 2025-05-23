# security_patches.py - Immediate security fixes

import os
import re
import subprocess
import sqlite3
from pathlib import Path
from typing import Optional, List
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class SecurityValidator:
    """Security validation utilities"""
    
    # Allowed domains for URL validation
    ALLOWED_DOMAINS = {
        'twitter.com', 'x.com', 'nitter.net', 'nitter.it', 'nitter.snopyta.org',
        'nitter.42l.fr', 'nitter.nixnet.services', 'nitter.eu', 'nitter.unixfox.eu'
    }
    
    # Maximum file sizes (bytes)
    MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_JSON_SIZE = 10 * 1024 * 1024   # 10MB
    
    @staticmethod
    def validate_status_id(status_id: str) -> bool:
        """Validate status ID is numeric and reasonable length"""
        if not status_id or not isinstance(status_id, str):
            return False
        if not status_id.isdigit():
            return False
        if len(status_id) < 10 or len(status_id) > 25:  # Twitter status IDs are ~19 digits
            return False
        return True
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL against allowed domains"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
                
            # Check if domain or parent domain is allowed
            for allowed in SecurityValidator.ALLOWED_DOMAINS:
                if domain == allowed or domain.endswith('.' + allowed):
                    return True
                    
            return False
        except Exception:
            return False
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent path traversal"""
        # Remove any directory separators and dangerous characters
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        sanitized = sanitized.replace('..', '_')
        sanitized = sanitized.strip('. ')
        
        # Ensure filename isn't empty after sanitization
        if not sanitized:
            sanitized = 'unnamed'
            
        return sanitized[:255]  # Limit filename length

class SecureDataManager:
    """Secure version of data manager with proper validation"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o750)  # Secure permissions
        
        # Set secure database path with restricted permissions
        self.db_path = self.data_dir / 'xread_data.db'
        self._ensure_secure_db()
    
    def _ensure_secure_db(self):
        """Ensure database file has secure permissions"""
        if self.db_path.exists():
            os.chmod(self.db_path, 0o640)  # rw-r-----
    
    def _get_secure_connection(self) -> sqlite3.Connection:
        """Get database connection with security settings"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0,
            isolation_level='IMMEDIATE'  # Better concurrency control
        )
        
        # Enable foreign key constraints for data integrity
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Better performance
        conn.execute("PRAGMA synchronous = NORMAL")  # Balance performance/safety
        
        return conn
    
    def validate_and_save_post(self, status_id: str, data: dict) -> bool:
        """Safely save post data with validation"""
        # Validate status ID
        if not SecurityValidator.validate_status_id(status_id):
            logger.error(f"Invalid status ID: {status_id}")
            return False
        
        # Sanitize status ID for filename
        clean_status_id = SecurityValidator.sanitize_filename(status_id)
        
        try:
            # Use parameterized query to prevent SQL injection
            conn = self._get_secure_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT OR REPLACE INTO posts 
                   (status_id, author, text, date, data_json) 
                   VALUES (?, ?, ?, ?, ?)""",
                (clean_status_id, data.get('author', ''), 
                 data.get('text', ''), data.get('date', ''), 
                 str(data)[:SecurityValidator.MAX_JSON_SIZE])
            )
            
            conn.commit()
            conn.close()
            
            # Save JSON file with secure path
            json_filename = f"post_{clean_status_id}.json"
            json_path = self.data_dir / 'scraped_data' / json_filename
            json_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            
            # Write with secure permissions
            with open(json_path, 'w', encoding='utf-8') as f:
                import json
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            os.chmod(json_path, 0o640)  # rw-r-----
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving post {status_id}: {e}")
            return False

class SecureUtilities:
    """Secure utility functions"""
    
    @staticmethod
    def safe_play_sound(sound_file: Path) -> bool:
        """Safely play notification sound without command injection"""
        if not sound_file.exists():
            logger.info("Sound file not found, skipping notification")
            return False
        
        # Use subprocess with explicit arguments (no shell injection possible)
        players = [
            ['mpg123', '-q', str(sound_file)],
            ['mpv', '--no-terminal', '--quiet', str(sound_file)],
            ['paplay', str(sound_file)],
            ['afplay', str(sound_file)]  # macOS
        ]
        
        for player_cmd in players:
            try:
                # Check if player exists
                result = subprocess.run(
                    [player_cmd[0], '--version'],
                    capture_output=True,
                    timeout=5,
                    check=False
                )
                
                if result.returncode == 0 or result.returncode == 1:  # Many players return 1 for --version
                    # Player exists, try to play sound
                    subprocess.Popen(
                        player_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    logger.info(f"Playing sound with {player_cmd[0]}")
                    return True
                    
            except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
                continue
        
        logger.warning("No suitable audio player found")
        return False

class ConfigSecurityChecker:
    """Check configuration for security issues"""
    
    @staticmethod
    def check_config_security(config_path: Path) -> List[str]:
        """Check configuration file for security issues"""
        issues = []
        
        if not config_path.exists():
            return issues
        
        try:
            with open(config_path, 'r') as f:
                content = f.read()
            
            # Check for API keys in config
            if 'api_key' in content.lower():
                issues.append("API keys found in config file - move to environment variables")
            
            # Check for hardcoded passwords
            if 'password' in content.lower():
                issues.append("Passwords found in config file")
            
            # Check for hardcoded URLs that might be sensitive
            sensitive_patterns = [
                r'https?://[^/]*localhost',
                r'https?://[^/]*127\.0\.0\.1',
                r'https?://[^/]*192\.168\.',
                r'https?://[^/]*10\.',
            ]
            
            for pattern in sensitive_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append("Internal/localhost URLs found in config")
            
        except Exception as e:
            issues.append(f"Error reading config file: {e}")
        
        return issues

# Environment variable validation
def validate_environment():
    """Validate environment variables for security"""
    required_env_vars = ['PERPLEXITY_API_KEY']
    missing_vars = []
    
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        return False
    
    # Validate API key format (basic check)
    perplexity_key = os.getenv('PERPLEXITY_API_KEY')
    if perplexity_key and not perplexity_key.startswith('pplx-'):
        logger.warning("Perplexity API key format appears invalid")
    
    return True

if __name__ == "__main__":
    # Quick security check
    checker = ConfigSecurityChecker()
    issues = checker.check_config_security(Path("config.ini"))
    
    if issues:
        print("SECURITY ISSUES FOUND:")
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("✅ No obvious security issues found in config")
    
    if validate_environment():
        print("✅ Environment variables look good")
    else:
        print("❌ Environment variable issues found")
