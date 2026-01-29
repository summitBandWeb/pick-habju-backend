import pytest
import os
from dotenv import load_dotenv
from app.repositories.supabase_repository import SupabaseFavoriteRepository

# Load environment variables
load_dotenv()

@pytest.fixture
def repo():
    """Real Supabase Repository instance"""
    return SupabaseFavoriteRepository()

@pytest.fixture
def test_data():
    """Test data tuple (using real IDs from DB to satisfy FK constraints)"""
    return ("550e8400-e29b-41d4-a716-446655440000", "sadang", "13")

def test_supabase_crud(repo, test_data):
    """
    Supabase CRUD Integration Test
    WARNING: This hits the real DB. Ensure test environment.
    """
    device_id, business_id, biz_item_id = test_data
    
    # 1. Clean up potential leftovers
    if repo.exists(device_id, business_id, biz_item_id):
        repo.delete(device_id, business_id, biz_item_id)
    
    # 2. Add
    assert repo.add(device_id, business_id, biz_item_id) is True
    
    # 3. Add Duplicate (Idempotency) -> Should return True (upsert success)
    assert repo.add(device_id, business_id, biz_item_id) is True 
    
    # 4. Exists
    assert repo.exists(device_id, business_id, biz_item_id) is True
    
    # 5. Get All
    items = repo.get_all(device_id)
    assert biz_item_id in items
    
    # 6. Delete
    repo.delete(device_id, business_id, biz_item_id)
    assert repo.exists(device_id, business_id, biz_item_id) is False
