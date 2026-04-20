import hashlib   # For hashing API keys
import secrets   # For generating secure random strings

def generate_raw_api_key(prefix: str = "syndra") -> str:
    """
    Generate a raw API key with the given prefix.
    
    Args:
        prefix: The prefix to use for the API key.
        
    Returns:
        The raw API key.

    Example:
        syndra_1234567890abcdef1234567890abcdef
    """

    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"

def get_api_key_hash(api_key: str) -> str:
    """
    Calculates the SHA-256 hash of the given API key (in plain text).
    
    Args:
        api_key: The API key to hash.
        
    Returns:
        The SHA-256 hash of the API key.
    """

    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()