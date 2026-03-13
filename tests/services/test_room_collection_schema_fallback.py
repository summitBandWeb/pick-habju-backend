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
    def __init__(self, room_table=None, branch_table=None):
        """왜: 컬럼 누락 예외 재현을 위해 최소 supabase 인터페이스만 흉내내고, 사용처: fallback 단위 테스트에서 table 라우팅에 사용한다."""
        self.room_table = room_table
        self.branch_table = branch_table

    def table(self, name: str):
        if name == "room":
            return self.room_table
        if name == "branch":
            return self.branch_table
        raise AssertionError(f"unexpected table: {name}")


def test_extract_missing_column_from_error_parses_postgrest_message():
    exc = Exception(
        "{'message': \"Could not find the 'requires_contact_on_sameday' column of 'room' in the schema cache\"}"
    )
    col = RoomCollectionService._extract_missing_column_from_error(exc)
    assert col == "requires_contact_on_sameday"


def test_upsert_room_fallback_removes_missing_column_and_retries():
    room_table = _RoomTableStub(
        first_error="{'message': \"Could not find the 'some_future_column' column of 'room' in the schema cache\"}"
    )
    service = object.__new__(RoomCollectionService)
    service.supabase = _SupabaseStub(room_table=room_table)
    service._unsupported_room_columns = set()
    service._unsupported_branch_columns = set()

    payload = {
        "business_id": "1061592",
        "biz_item_id": "5587861",
        "some_future_column": "value",
        "requires_call_on_sameday": False,
    }

    service._upsert_room_with_schema_fallback(payload)

    assert room_table.call_count == 2
    assert "some_future_column" in room_table.payloads[0]
    assert "some_future_column" not in room_table.payloads[1]
    assert "requires_call_on_sameday" in room_table.payloads[1]


def test_upsert_room_fallback_reraises_unrelated_errors():
    room_table = _RoomTableStub(first_error="permission denied")
    service = object.__new__(RoomCollectionService)
    service.supabase = _SupabaseStub(room_table=room_table)
    service._unsupported_room_columns = set()
    service._unsupported_branch_columns = set()

    payload = {"business_id": "1061592", "biz_item_id": "5587861"}

    try:
        service._upsert_room_with_schema_fallback(payload)
    except Exception as exc:
        assert "permission denied" in str(exc)
    else:
        raise AssertionError("Expected exception was not raised")


def test_upsert_branch_fallback_removes_missing_column_and_retries():
    """왜: branch optional 컬럼 누락 시 수집 중단을 막아야 하며, 사용처: _upsert_branch_with_schema_fallback 재시도 동작을 검증한다."""
    branch_table = _RoomTableStub(
        first_error="{'message': \"Could not find the 'phone_number' column of 'branch' in the schema cache\"}"
    )
    service = object.__new__(RoomCollectionService)
    service.supabase = _SupabaseStub(branch_table=branch_table)
    service._unsupported_room_columns = set()
    service._unsupported_branch_columns = set()

    payload = {
        "business_id": "1061592",
        "name": "테스트 합주실",
        "display_name": "테스트 합주실",
        "phone_number": "02-123-4567",
    }

    service._upsert_branch_with_schema_fallback(payload)

    assert branch_table.call_count == 2
    assert "phone_number" in branch_table.payloads[0]
    assert "phone_number" not in branch_table.payloads[1]
    assert "display_name" in branch_table.payloads[1]
