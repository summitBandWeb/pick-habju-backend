from app.services.room_collection_service import RoomCollectionService


class _ExecResult:
    def __init__(self, error_message=None):
        self.error_message = error_message

    def execute(self):
        if self.error_message:
            raise Exception(self.error_message)
        return {"ok": True}


class _RoomTableStub:
    def __init__(self, first_error=None):
        self.first_error = first_error
        self.call_count = 0
        self.payloads = []

    def upsert(self, payload):
        self.call_count += 1
        self.payloads.append(dict(payload))
        if self.call_count == 1 and self.first_error:
            return _ExecResult(self.first_error)
        return _ExecResult()


class _SupabaseStub:
    def __init__(self, room_table):
        self.room_table = room_table

    def table(self, name: str):
        assert name == "room"
        return self.room_table


def test_extract_missing_column_from_error_parses_postgrest_message():
    exc = Exception(
        "{'message': \"Could not find the 'requires_contact_on_sameday' column of 'room' in the schema cache\"}"
    )
    col = RoomCollectionService._extract_missing_column_from_error(exc)
    assert col == "requires_contact_on_sameday"


def test_upsert_room_fallback_removes_missing_column_and_retries():
    room_table = _RoomTableStub(
        first_error="{'message': \"Could not find the 'requires_contact_on_sameday' column of 'room' in the schema cache\"}"
    )
    service = object.__new__(RoomCollectionService)
    service.supabase = _SupabaseStub(room_table)
    service._unsupported_room_columns = set()

    payload = {
        "business_id": "1061592",
        "biz_item_id": "5587861",
        "requires_contact_on_sameday": False,
        "requires_contact_same_day": False,
    }

    service._upsert_room_with_schema_fallback(payload)

    assert room_table.call_count == 2
    assert "requires_contact_on_sameday" in room_table.payloads[0]
    assert "requires_contact_on_sameday" not in room_table.payloads[1]
    assert "requires_contact_same_day" in room_table.payloads[1]


def test_upsert_room_fallback_reraises_unrelated_errors():
    room_table = _RoomTableStub(first_error="permission denied")
    service = object.__new__(RoomCollectionService)
    service.supabase = _SupabaseStub(room_table)
    service._unsupported_room_columns = set()

    payload = {"business_id": "1061592", "biz_item_id": "5587861"}

    try:
        service._upsert_room_with_schema_fallback(payload)
    except Exception as exc:
        assert "permission denied" in str(exc)
    else:
        raise AssertionError("Expected exception was not raised")
