from neeshops.conversation.intent import detect_route


def test_buying_specific_request():
    result = detect_route(
        "I want black running shoes under $120",
        previous_route=None,
        constraint_count=3,
    )
    assert result == "buying"


def test_buying_with_hard_constraints():
    result = detect_route(
        "I need a size 9 waterproof jacket",
        previous_route=None,
        constraint_count=3,
    )
    assert result == "buying"


def test_browsing_open_ended_request():
    result = detect_route(
        "I'm looking for something nice for a casual weekend",
        previous_route=None,
        constraint_count=0,
    )
    assert result == "browsing"


def test_browsing_exploratory_request():
    result = detect_route(
        "I just want to browse and get some inspiration",
        previous_route=None,
        constraint_count=0,
    )
    assert result == "browsing"

def test_buying_after_browsing_when_specific_constraints_appear():
    result = detect_route(
        "Actually I need a black dress under $100",
        previous_route="browsing",
        constraint_count=3,
    )
    assert result == "buying"


def test_browsing_stays_browsing_when_request_is_vague():
    result = detect_route(
        "Actually, just show me some ideas",
        previous_route="browsing",
        constraint_count=0,
    )
    assert result == "browsing"


def test_buying_stays_buying_with_more_constraints():
    result = detect_route(
        "Actually make it Nike, size 9",
        previous_route="buying",
        constraint_count=2,
    )
    assert result == "buying"


def test_no_preference_does_not_create_buying_intent():
    result = detect_route(
        "I don't have a preference for color",
        previous_route=None,
        constraint_count=0,
    )
    assert result == "browsing"

