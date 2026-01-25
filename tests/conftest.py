from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


class MockCollection:
    """In-memory mock MongoDB collection for testing."""

    def __init__(self):
        self.documents = []
        self._id_counter = 0

    async def insert_one(self, document):
        self._id_counter += 1
        doc = {"_id": document.get("_id", self._id_counter), **document}
        self.documents.append(doc)
        return MagicMock(inserted_id=doc["_id"])

    async def update_one(self, filter_query, update, upsert=False):
        for doc in self.documents:
            if all(doc.get(k) == v for k, v in filter_query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                return MagicMock(modified_count=1, upserted_id=None)

        if upsert:
            new_doc = {**filter_query, **update.get("$set", {})}
            if "_id" in filter_query:
                new_doc["_id"] = filter_query["_id"]
            self.documents.append(new_doc)
            return MagicMock(modified_count=0, upserted_id=new_doc.get("_id"))

        return MagicMock(modified_count=0, upserted_id=None)

    async def find_one(self, filter_query=None, sort=None):
        matches = self._filter(filter_query or {})
        if sort:
            field, direction = sort[0]
            matches.sort(key=lambda x: x.get(field, 0), reverse=(direction == -1))
        return matches[0] if matches else None

    async def count_documents(self, filter_query):
        return len(self._filter(filter_query))

    def aggregate(self, pipeline):
        return MockCursor(self._run_aggregate(pipeline))

    async def create_index(self, keys):
        pass  # No-op for testing

    def _filter(self, filter_query):
        results = []
        for doc in self.documents:
            match = True
            for key, value in filter_query.items():
                if isinstance(value, dict):
                    # Handle operators like $ne, $exists
                    for op, op_value in value.items():
                        if op == "$ne" and doc.get(key) == op_value:
                            match = False
                        elif op == "$exists" and op_value and key not in doc:
                            match = False
                        elif op == "$exists" and not op_value and key in doc:
                            match = False
                elif doc.get(key) != value:
                    match = False
            if match:
                results.append(doc)
        return results

    def _run_aggregate(self, pipeline):
        results = list(self.documents)

        for stage in pipeline:
            if "$match" in stage:
                results = [
                    doc for doc in results
                    if self._matches_filter(doc, stage["$match"])
                ]
            elif "$group" in stage:
                results = self._group(results, stage["$group"])
            elif "$unwind" in stage:
                results = self._unwind(results, stage["$unwind"])
            elif "$sort" in stage:
                for field, direction in reversed(list(stage["$sort"].items())):
                    results.sort(
                        key=lambda x: x.get(field, 0),
                        reverse=(direction == -1)
                    )
            elif "$limit" in stage:
                results = results[: stage["$limit"]]

        return results

    def _get_nested_value(self, doc, key):
        """Get a value from a nested path like 'emojis.0' or 'user.name'."""
        parts = key.split(".")
        value = doc
        for part in parts:
            if value is None:
                return None
            if isinstance(value, list):
                try:
                    value = value[int(part)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value

    def _has_nested_key(self, doc, key):
        """Check if a nested path exists in the document."""
        parts = key.split(".")
        value = doc
        for part in parts:
            if value is None:
                return False
            if isinstance(value, list):
                try:
                    idx = int(part)
                    if idx >= len(value):
                        return False
                    value = value[idx]
                except (ValueError, IndexError):
                    return False
            elif isinstance(value, dict):
                if part not in value:
                    return False
                value = value.get(part)
            else:
                return False
        return True

    def _matches_filter(self, doc, filter_query):
        for key, value in filter_query.items():
            if isinstance(value, dict):
                for op, op_value in value.items():
                    if op == "$ne" and self._get_nested_value(doc, key) == op_value:
                        return False
                    elif op == "$exists":
                        has_key = self._has_nested_key(doc, key)
                        if op_value and not has_key:
                            return False
                        if not op_value and has_key:
                            return False
            elif self._get_nested_value(doc, key) != value:
                return False
        return True

    def _group(self, docs, group_spec):
        groups = {}
        group_id = group_spec["_id"]

        for doc in docs:
            if group_id is None:
                key = None
            elif isinstance(group_id, str) and group_id.startswith("$"):
                key = doc.get(group_id[1:])
            else:
                key = group_id

            if key not in groups:
                groups[key] = {"_id": key}
                for field, op in group_spec.items():
                    if field == "_id":
                        continue
                    if isinstance(op, dict) and "$sum" in op:
                        groups[key][field] = 0

            for field, op in group_spec.items():
                if field == "_id":
                    continue
                if isinstance(op, dict):
                    if "$sum" in op:
                        if op["$sum"] == 1:
                            groups[key][field] += 1
                        elif isinstance(op["$sum"], str) and op["$sum"].startswith("$"):
                            groups[key][field] += doc.get(op["$sum"][1:], 0)

        return list(groups.values())

    def _unwind(self, docs, unwind_spec):
        if isinstance(unwind_spec, str):
            field = unwind_spec.lstrip("$")
        else:
            field = unwind_spec["path"].lstrip("$")

        results = []
        for doc in docs:
            arr = doc.get(field, [])
            if isinstance(arr, list):
                for item in arr:
                    new_doc = {**doc, field: item}
                    results.append(new_doc)
        return results


class MockCursor:
    """Mock async cursor for aggregate results."""

    def __init__(self, results):
        self.results = results

    async def to_list(self, length=None):
        if length:
            return self.results[:length]
        return self.results


class MockDatabase:
    """Mock MongoDB database with collections."""

    def __init__(self):
        self.users = MockCollection()
        self.voice_sessions = MockCollection()
        self.messages = MockCollection()
        self.reactions = MockCollection()


@pytest.fixture
def mock_db(monkeypatch):
    """Fixture that provides a mock database and patches the db module."""
    mock = MockDatabase()
    monkeypatch.setattr("db.db", mock)
    return mock


@pytest.fixture
def sample_user_id():
    return "123456789"


@pytest.fixture
def sample_guild_id():
    return "987654321"


@pytest.fixture
def sample_timestamp():
    return datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
