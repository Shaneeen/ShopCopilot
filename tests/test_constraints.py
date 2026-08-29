from neeshops.conversation.constraints import extract_constraints
from neeshops.models.session import NO_PREFERENCE


def test_extract_constraints():
    cases = [
        ("I want black shoes", {"color": "black"}),
        ("I want red hat", {"color": "red"}),
        ("I want white shoes", {"color": "white"}),
        ("I want running shoes", {"category": "shoes"}),
        ("I want leather shoes", {"material": "leather"}),
        ("I want size 9 shoes", {"size": "9"}),
        ("I want casual shirt", {"style": "casual"}),
        ("I want Nike shoes", {"brand": "nike"}),
        ("I want a waterproof jacket", {"feature": "waterproof"}),
        ("I need a dress for a wedding", {"use_case": "wedding"}),
        ("I have a budget of $100", {"budget": 100.0}),
        ("my budget is up to $120", {"budget": 120.0}),
        ("I can spend a maximum of $80", {"budget": 80.0}),
        ("I don't care about the color", {"color": NO_PREFERENCE}),
        ("any material is fine", {"material": NO_PREFERENCE}),
        ("I don't mind which brand", {"brand": NO_PREFERENCE}),
    ]

    for message, expected in cases:
        result = extract_constraints(message)

        for field, value in expected.items():
            assert result.get(field) == value