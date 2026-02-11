from noty.filters.reaction_decider import ReactionDecider


def test_reaction_decider_stats_progress():
    decider = ReactionDecider(target_rate=0.5)
    for _ in range(10):
        decider.decide(semantic_score=0.95, heuristic_boost=0.0)

    stats = decider.stats()
    assert stats["seen"] == 10
    assert 0 <= stats["response_rate"] <= 1
    assert 0.35 <= stats["adaptive_threshold"] <= 0.8
