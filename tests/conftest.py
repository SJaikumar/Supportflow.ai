"""Point the application modules at a temporary database before import."""
import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

@pytest.fixture(scope='session')
def demo(tmp_path_factory):
    path=tmp_path_factory.mktemp('supportflow')/'supportflow_test.sqlite'
    os.environ['SUPPORTFLOW_DB_PATH']=str(path)
    from supportflow.seed import seed_if_empty, seed_stage2_examples_if_missing
    from supportflow import services
    assert seed_if_empty() is True
    assert seed_stage2_examples_if_missing() is True
    return services
