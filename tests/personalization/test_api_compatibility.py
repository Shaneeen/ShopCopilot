from neeshops.models.session import UserProfile
from neeshops.personalization.profile import personalization_boost


def test_existing_3a_import_and_argument_order_remain_compatible():
    product_row = {"title": "Comfort running shoe", "categories": ["Shoes"]}
    profile = UserProfile(preference_tags=["comfort"])
    result = personalization_boost(product_row, profile)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0
