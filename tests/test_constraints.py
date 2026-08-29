from neeshops.conversation.constraints import extract_constraints


def test_extract_constraints():
    cases = [
        ("I want black shoes", {"color": "black"}),
        ("I want red shoes", {"color": "red"}),
        ("I want white shoes", {"color": "white"}),
        ("I want running shoes", {"category": "shoes"}),
        ("I want leather shoes", {"material": "leather"}),
        ("I want size 9 shoes", {"size": "9"}),
    ]

    for message, expected in cases:
        result = extract_constraints(message)

        for field, value in expected.items():
            assert result.get(field) == value