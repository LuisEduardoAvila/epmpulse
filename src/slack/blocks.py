"""Canvas block generators for EPMPulse Slack integration."""

from typing import Dict, Any, Optional
from datetime import datetime


# Status to icon mapping
STATUS_ICONS = {
    'Blank': '⚪',
    'Loading': '🟡',
    'OK': '🟢',
    'Warning': '🔴',
}


def build_header_block(app_name: str, display_name: str) -> Dict[str, Any]:
    """Build header block for an application section.
    
    Args:
        app_name: Application name
        display_name: Display name for the application
        
    Returns:
        Header block dictionary with block_id for section updates
    """
    return {
        'type': 'section',
        'block_id': f"{app_name.lower()}_header",
        'text': {
            'type': 'mrkdwn',
            'text': f'*▸ {display_name}*'
        }
    }


def build_status_field_block(domain_name: str, status: str, job_id: Optional[str] = None, updated: Optional[str] = None) -> Dict[str, Any]:
    """Build a status field block for domain status.
    
    Args:
        domain_name: Name of the domain
        status: Current status (Blank, Loading, OK, Warning)
        job_id: Optional job ID
        updated: Optional last updated timestamp
        
    Returns:
        Section block with fields dictionary
    """
    status_icon = STATUS_ICONS.get(status, '⚪')
    status_text = f'{status_icon} {status}'
    
    # Build context text
    context_parts = [f'_{domain_name}_']
    
    if job_id:
        context_parts.append(f'Job: {job_id}')
    
    if updated:
        try:
            # Parse timestamp and calculate relative time
            updated_dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
            now = datetime.now(updated_dt.tzinfo or datetime.now().astimezone().tzinfo)
            delta = now - updated_dt
            seconds = int(delta.total_seconds())
            
            if seconds < 60:
                context_parts.append(f'{seconds}s ago')
            elif seconds < 3600:
                context_parts.append(f'{seconds // 60}m ago')
            else:
                context_parts.append(f'{seconds // 3600}h ago')
        except (ValueError, TypeError):
            context_parts.append(f'updated')
    
    return {
        'type': 'section',
        'fields': [
            {
                'type': 'mrkdwn',
                'text': status_text
            },
            {
                'type': 'mrkdwn',
                'text': '\n'.join(context_parts)
            }
        ]
    }


def build_divider_block() -> Dict[str, Any]:
    """Build a divider block.
    
    Returns:
        Divider block dictionary
    """
    return {'type': 'divider'}


def build_dashboard_header_block() -> Dict[str, Any]:
    """Build the dashboard header.
    
    Returns:
        Header block dictionary
    """
    return {
        'type': 'header',
        'text': {
            'type': 'plain_text',
            'text': '📊 EPM Status Dashboard',
            'emoji': True
        }
    }


def build_footer_block(last_updated: Optional[str] = None) -> Dict[str, Any]:
    """Build the dashboard footer.
    
    Args:
        last_updated: Optional last update timestamp
        
    Returns:
        Context block dictionary
    """
    text = '🔄 Auto-refresh on job events'
    if last_updated:
        try:
            updated_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            text = f'Last updated: {updated_dt.strftime("%H:%M GMT")} | {text}'
        except (ValueError, TypeError):
            pass
    
    return {
        'type': 'context',
        'elements': [
            {
                'type': 'mrkdwn',
                'text': text
            }
        ]
    }


def build_domain_section(app_name: str, domain_name: str, domain_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build complete section for a domain.
    
    Args:
        app_name: Application name
        domain_name: Domain name
        domain_data: Domain status data
        
    Returns:
        Complete section block dictionary with block_id for section updates
    """
    status = domain_data.get('status', 'Blank')
    job_id = domain_data.get('job_id')
    updated = domain_data.get('updated')
    
    block = build_status_field_block(
        domain_name=domain_name,
        status=status,
        job_id=job_id,
        updated=updated
    )
    
    # Add block_id for section-based updates
    block['block_id'] = f"{app_name.lower()}_{domain_name.lower()}_section"
    
    return block


def build_single_domain_blocks(
    app_name: str,
    display_name: str,
    domain_name: str,
    domain_data: Dict[str, Any]
) -> list:
    """Build blocks for a single domain update with proper block_ids.
    
    Args:
        app_name: Application name
        display_name: Display name for the app
        domain_name: Domain name
        domain_data: Domain status data
        
    Returns:
        List of block dictionaries with block_ids for section updates
    """
    blocks = []
    
    # Header with block_id
    blocks.append(build_header_block(app_name, display_name))
    
    # Single domain section with unique block_id
    domain_block = build_domain_section(app_name, domain_name, domain_data)
    blocks.append(domain_block)
    
    return blocks


def build_app_block(
    app_name: str,
    display_name: str,
    domains: Dict[str, Dict[str, Any]]
) -> list:
    """Build all blocks for an application.
    
    Args:
        app_name: Application name
        display_name: Display name
        domains: Dictionary of domain data
        
    Returns:
        List of block dictionaries with block_ids for section updates
    """
    blocks = []
    
    # Header with block_id for section updates
    blocks.append(build_header_block(app_name, display_name))
    
    # Status fields (2 per row) with unique block_ids
    domain_list = list(domains.items())
    for i in range(0, len(domain_list), 2):
        domain_pairs = domain_list[i:i+2]
        
        # Build fields list
        fields = []
        block_id_parts = []
        for domain_name, domain_data in domain_pairs:
            status = domain_data.get('status', 'Blank')
            job_id = domain_data.get('job_id')
            updated = domain_data.get('updated')
            
            status_icon = STATUS_ICONS.get(status, '⚪')
            status_text = f'{status_icon} {status}'
            
            context_parts = [f'_{domain_name}_']
            if job_id:
                context_parts.append(f'Job: {job_id}')
            if updated:
                context_parts.append(f'{updated}')
            
            fields.append({
                'type': 'mrkdwn',
                'text': '\n'.join(context_parts)
            })
            fields.append({
                'type': 'mrkdwn',
                'text': status_text
            })
            
            # Collect domain names for block_id
            block_id_parts.append(domain_name.lower())
        
        # Create unique block_id for this section
        domains_str = '_'.join(sorted(block_id_parts))
        block_id = f"{app_name.lower()}_{domains_str}_section"
        
        blocks.append({
            'type': 'section',
            'block_id': block_id,
            'fields': fields
        })
    
    return blocks


def build_canvas_state(state_data: Dict[str, Any]) -> list:
    """Build complete canvas blocks from state data.
    
    Args:
        state_data: Full state dictionary with apps
                
    Returns:
        List of all canvas blocks
    """
    blocks = []
    
    # Header
    blocks.append(build_dashboard_header_block())
    blocks.append(build_footer_block(state_data.get('last_updated')))
    blocks.append(build_divider_block())
    
    # Application sections
    apps = state_data.get('apps', {})
    for app_name, app_data in apps.items():
        display_name = app_data.get('display_name', app_name)
        domains = app_data.get('domains', {})
        
        blocks.extend(build_app_block(app_name, display_name, domains))
        blocks.append(build_divider_block())
    
    # Footer
    blocks.append(build_footer_block(state_data.get('last_updated')))
    
    return blocks
