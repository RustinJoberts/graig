from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


class MockCollection:
    """In-memory mock MongoDB collection for testing."""

    def __init__(self):
        self.documents = []
        self._id_counter = 0
        self._all_collections = None

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
        return MockCursor(self._run_aggregate(pipeline, self._all_collections))

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

    def _run_aggregate(self, pipeline, all_collections=None):
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
            elif "$lookup" in stage:
                results = self._lookup(results, stage["$lookup"], all_collections)
            elif "$project" in stage:
                results = self._project(results, stage["$project"])

        return results

    def _lookup(self, docs, lookup_spec, all_collections=None):
        """Perform a $lookup join operation."""
        from_coll = lookup_spec.get("from")
        local_field = lookup_spec.get("localField")
        foreign_field = lookup_spec.get("foreignField")
        as_field = lookup_spec.get("as")

        # Get the foreign collection from all_collections if available
        foreign_docs = []
        if all_collections and from_coll in all_collections:
            foreign_docs = all_collections[from_coll].documents

        results = []
        for doc in docs:
            local_value = doc.get(local_field)
            matches = [
                fdoc for fdoc in foreign_docs
                if fdoc.get(foreign_field) == local_value
            ]
            new_doc = {**doc, as_field: matches}
            results.append(new_doc)
        return results

    def _project(self, docs, project_spec):
        """Perform a $project operation."""
        results = []
        for doc in docs:
            new_doc = {}
            for field, value in project_spec.items():
                if value == 1:
                    if field in doc:
                        new_doc[field] = doc[field]
                elif isinstance(value, str) and value.startswith("$"):
                    # Direct field reference
                    source_field = value[1:]
                    new_doc[field] = doc.get(source_field)
                elif isinstance(value, dict) and "$arrayElemAt" in value:
                    # Handle $arrayElemAt
                    arr_spec = value["$arrayElemAt"]
                    arr_field = arr_spec[0].lstrip("$")
                    arr_index = arr_spec[1]
                    # Handle nested path like "user_info.username"
                    parts = arr_field.split(".")
                    arr = doc.get(parts[0], [])
                    if arr and len(arr) > arr_index:
                        elem = arr[arr_index]
                        if len(parts) > 1:
                            new_doc[field] = elem.get(parts[1])
                        else:
                            new_doc[field] = elem
                    else:
                        new_doc[field] = None
            # Always include _id unless explicitly excluded
            if "_id" not in project_spec and "_id" in doc:
                new_doc["_id"] = doc["_id"]
            results.append(new_doc)
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
                doc_value = self._get_nested_value(doc, key)
                for op, op_value in value.items():
                    if op == "$ne" and doc_value == op_value:
                        return False
                    elif op == "$exists":
                        has_key = self._has_nested_key(doc, key)
                        if op_value and not has_key:
                            return False
                        if not op_value and has_key:
                            return False
                    elif op == "$gte" and (doc_value is None or doc_value < op_value):
                        return False
                    elif op == "$lte" and (doc_value is None or doc_value > op_value):
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
        # Link collections to each other for $lookup support
        all_collections = {
            "users": self.users,
            "voice_sessions": self.voice_sessions,
            "messages": self.messages,
            "reactions": self.reactions,
        }
        self.users._all_collections = all_collections
        self.voice_sessions._all_collections = all_collections
        self.messages._all_collections = all_collections
        self.reactions._all_collections = all_collections


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
