"""Slack SDK wrapper with retry logic for EPMPulse."""

import time
from typing import Optional, List, Dict, Any
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# SlackRateLimitError may be named differently in newer slack-sdk versions
try:
    from slack_sdk.errors import SlackRateLimitError
except ImportError:
    # Fallback: create a simple exception class if not available
    class SlackRateLimitError(SlackApiError):
        pass


class SlackClient:
    """Slack client with automatic retry and rate limit handling."""
    
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BACKOFF_SECONDS = [1, 2, 4]
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: Optional[List[int]] = None
    ):
        """Initialize Slack client.
        
        Args:
            bot_token: Slack bot token (reads from env if not provided)
            max_retries: Maximum retry attempts
            backoff_seconds: List of backoff delays for retries
        """
        self.bot_token = bot_token or self._get_token_from_env()
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds or self.DEFAULT_BACKOFF_SECONDS
        
        self.client = None
        if self.bot_token:
            self.client = WebClient(token=self.bot_token)
    
    def _get_token_from_env(self) -> Optional[str]:
        """Get Slack bot token from environment."""
        import os
        return os.environ.get('SLACK_BOT_TOKEN')
    
    def is_configured(self) -> bool:
        """Check if client is properly configured."""
        return self.client is not None
    
    def test_connection(self) -> bool:
        """Test Slack API connection."""
        if not self.is_configured():
            return False
        
        try:
            self.client.auth_test()
            return True
        except SlackApiError:
            return False
    
    def _make_request_with_retry(self, method, *args, **kwargs) -> Optional[Any]:
        """Make API request with retry logic.
        
        Args:
            method: Slack SDK method to call
            *args: Positional arguments for method
            **kwargs: Keyword arguments for method
            
        Returns:
            Method response or None if all retries failed
        """
        if not self.is_configured():
            raise RuntimeError("Slack client not configured")
        
        for attempt in range(self.max_retries):
            try:
                return method(*args, **kwargs)
            except SlackRateLimitError as e:
                if attempt < self.max_retries - 1:
                    backoff = self.backoff_seconds[attempt % len(self.backoff_seconds)]
                    time.sleep(backoff)
                else:
                    raise
            except SlackApiError as e:
                if attempt < self.max_retries - 1:
                    backoff = self.backoff_seconds[attempt % len(self.backoff_seconds)]
                    time.sleep(backoff)
                else:
                    raise
    
    def update_canvas_section(
        self,
        canvas_id: str,
        section_id: str,
        content: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Update a specific canvas section.
        
        Args:
            canvas_id: Canvas ID to update
            section_id: Section ID to update
            content: New markdown content (optional)
            blocks: Block kit blocks to update section with (optional)
            
        Returns:
            True if successful, False otherwise
        """
        if not content and not blocks:
            print("Canvas section update failed: must provide content or blocks")
            return False
        
        try:
            kwargs = {
                'canvas_id': canvas_id,
                'section_id': section_id,
            }
            if content:
                kwargs['content'] = content
            if blocks:
                kwargs['blocks'] = blocks
            
            self.client.canvases_section_update(**kwargs)
            return True
        except AttributeError:
            # canvases_section_update not available in this SDK version
            print("Warning: canvases_section_update not available in Slack SDK version")
            return False
        except SlackApiError as e:
            print(f"Canvas section update failed: {e}")
            return False
    
    def get_canvas(self, canvas_id: str) -> Optional[Dict[str, Any]]:
        """Get canvas details.
        
        Args:
            canvas_id: Canvas ID to retrieve
            
        Returns:
            Canvas data or None if not found
        """
        try:
            return self.client.canvases_info(canvas_id=canvas_id)
        except SlackApiError:
            return None
    
    def list_channels(self) -> List[Dict[str, Any]]:
        """List all channels the bot can see.
        
        Returns:
            List of channel data dictionaries
        """
        try:
            channels = []
            cursor = None
            
            while True:
                result = self.client.conversations_list(
                    cursor=cursor,
                    types=['public_channel', 'private_channel']
                )
                
                channels.extend(result.get('channels', []))
                
                cursor = result.get('response_metadata', {}).get('next_cursor')
                if not cursor:
                    break
            
            return channels
        except SlackApiError:
            return []
