"""CPU profiling with py-spy integration.

Provides on-demand CPU profiling for performance analysis.
Requires PROFILE_ADMIN_TOKEN environment variable for authentication.
"""

import logging
import os
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Profile storage directory
PROFILE_DIR = Path(os.getenv('PROFILE_DIR', '/var/lib/graphiti/profiles'))
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# Active profiling session
_active_session = {}


class ProfilingError(Exception):
    """Profiling operation failed."""
    pass


def start_profiling(duration: int = 30) -> str:
    """Start CPU profiling for the specified duration.
    
    Args:
        duration: Profiling duration in seconds (default: 30)
    
    Returns:
        Profile ID for later retrieval
    
    Raises:
        ProfilingError: If profiling is already active or fails to start
    """
    global _active_session
    
    if _active_session:
        raise ProfilingError('Profiling already in progress')
    
    profile_id = str(uuid.uuid4())
    output_file = PROFILE_DIR / f'{profile_id}.svg'
    pid = os.getpid()
    
    try:
        # Start py-spy in background
        cmd = [
            'py-spy', 'record',
            '-o', str(output_file),
            '--pid', str(pid),
            '--duration', str(duration),
            '--format', 'svg'
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        _active_session = {
            'profile_id': profile_id,
            'process': process,
            'output_file': output_file,
            'started_at': datetime.utcnow(),
            'duration': duration
        }
        
        logger.info(f'Started profiling session {profile_id} for {duration}s')
        return profile_id
        
    except FileNotFoundError:
        raise ProfilingError('py-spy not found. Install with: pip install py-spy')
    except Exception as e:
        raise ProfilingError(f'Failed to start profiling: {e}')


def stop_profiling() -> Optional[str]:
    """Stop active profiling session.
    
    Returns:
        Profile ID if stopped successfully, None if no active session
    """
    global _active_session
    
    if not _active_session:
        return None
    
    process = _active_session['process']
    profile_id = _active_session['profile_id']
    
    try:
        process.terminate()
        process.wait(timeout=5)
        logger.info(f'Stopped profiling session {profile_id}')
    except subprocess.TimeoutExpired:
        process.kill()
        logger.warning(f'Force killed profiling session {profile_id}')
    
    _active_session = {}
    return profile_id


def get_profiling_status() -> dict:
    """Get current profiling status.
    
    Returns:
        Dict with profiling status information
    """
    if not _active_session:
        return {'active': False}
    
    started_at = _active_session['started_at']
    duration = _active_session['duration']
    elapsed = (datetime.utcnow() - started_at).total_seconds()
    
    return {
        'active': True,
        'profile_id': _active_session['profile_id'],
        'started_at': started_at.isoformat(),
        'duration': duration,
        'elapsed': elapsed,
        'remaining': max(0, duration - elapsed)
    }


def get_profile_file(profile_id: str) -> Optional[Path]:
    """Get profile file path.
    
    Args:
        profile_id: Profile ID
    
    Returns:
        Path to profile file if exists, None otherwise
    """
    profile_file = PROFILE_DIR / f'{profile_id}.svg'
    return profile_file if profile_file.exists() else None


def list_profiles() -> list[dict]:
    """List all available profiles.
    
    Returns:
        List of profile metadata
    """
    profiles = []
    for file in PROFILE_DIR.glob('*.svg'):
        stat = file.stat()
        profiles.append({
            'profile_id': file.stem,
            'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'size_bytes': stat.st_size
        })
    
    return sorted(profiles, key=lambda x: x['created_at'], reverse=True)
