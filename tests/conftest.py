import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starter.agent import Agent


@pytest.fixture(scope="module")
def agent_module():
    return Agent()


@pytest.fixture
def unique_session_id():
    return f"test-{uuid.uuid4().hex[:8]}"
