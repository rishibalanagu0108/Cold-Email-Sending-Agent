from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from outreach.db import Base, create_database_engine


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
        db_session.rollback()
    engine.dispose()
