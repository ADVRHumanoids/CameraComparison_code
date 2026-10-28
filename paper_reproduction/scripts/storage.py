"""Create staging directories without deleting failed or completed temporary work.

Used by download, extraction, analysis and rendering to preserve existing files
and comply with the no-deletion run. Successful publication moves staged files;
remaining directories and failed work are retained for inspection.
"""

from contextlib import contextmanager
import tempfile


@contextmanager
def staging_directory(*, prefix, dir):
    """Keep staging on every exit; callers publish completed artifacts by rename."""
    yield tempfile.mkdtemp(prefix=prefix, dir=dir)
