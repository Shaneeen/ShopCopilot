from neeshops.conversation.constraints import extract_constraints


def test_extract_constraints():
    cases = [
        ("I want black shoes", {"color": "black"}),
        ("I want red shoes", {"color": "red"}),
        ("I want white shoes", {"color": "white"}),
        ("I want running shoes", {"category": "shoes"}),
    ]

    for message, expected in cases:
        result = extract_constraints(message)

        for field, value in expected.items():
            assert result.get(field) == value