# EPMPulse API Key Generator
"""Generate API keys for EPMPulse."""

import secrets
import sys


def generate_api_key(prefix: str = 'epmpulse_key_') -> str:
    """Generate a secure API key.
    
    Args:
        prefix: Optional prefix for the key
        
    Returns:
        Generated API key
    """
    return prefix + secrets.token_hex(16)


def main():
    """Main entry point."""
    prefix = sys.argv[1] if len(sys.argv) > 1 else 'epmpulse_key_'
    key = generate_api_key(prefix)
    print(f"Generated API Key: {key}")
    print(f"\nSet as environment variable:")
    print(f"export EPMPULSE_API_KEY='{key}'")
    print(f"\nUsage in EPM Groovy rules:")
    print(f"String API_KEY = '{key}'")


if __name__ == '__main__':
    main()
