"""worldfootballpy: port a Python de worldfootballR."""

from ._http import get_user_agent, set_user_agent
from .fbref import *  # noqa: F401,F403

__version__ = "0.1.0"
