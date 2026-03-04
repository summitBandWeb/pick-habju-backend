from scripts.fix_branch_name_room_collision import is_placeholder_name

def test_is_placeholder_name_rejects_business_id_format():
    assert is_placeholder_name("business-123", "123") is True
    assert is_placeholder_name("123", "123") is True
    assert is_placeholder_name("BUSINESS-123", "123") is True
    assert is_placeholder_name(" 123 ", "123") is True

def test_is_placeholder_name_accepts_valid_names():
    assert is_placeholder_name("business-123", "456") is False
    assert is_placeholder_name("비쥬 합주실 123호점", "123") is False
    assert is_placeholder_name("합주실123", "123") is False
