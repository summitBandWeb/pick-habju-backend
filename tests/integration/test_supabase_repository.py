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
    """Test data tuple"""
    return ("test-device-uuid", "test-biz-id", "test-item-id")

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
    
    # 3. Add Duplicate (Idempotency) -> Should return False (or True if logic changed to upsert success?)
    # Upsert logic returns True if successful (created or updated). 
    # Current implementation returns len(data) > 0.
    assert repo.add(device_id, business_id, biz_item_id) is True 
    
    # 4. Exists
    assert repo.exists(device_id, business_id, biz_item_id) is True
    
    # 5. Get All
    items = repo.get_all(device_id)
    assert biz_item_id in items
    
    # 6. Delete
    repo.delete(device_id, business_id, biz_item_id)
    assert repo.exists(device_id, business_id, biz_item_id) is False
