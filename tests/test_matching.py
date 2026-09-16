from cdq.matching import Candidate, blocking_key, cluster, score_pair, token_set_ratio


def candidate(record_id, name, state="CA", phone=None, address=None):
    return Candidate(record_id, name, state, phone, address)


def test_token_set_ratio_ignores_word_order():
    assert token_set_ratio("ACME WIDGETS", "WIDGETS ACME") == 1.0


def test_token_set_ratio_penalises_extra_words():
    assert token_set_ratio("ACME WIDGETS", "ACME WIDGETS HOLDINGS") < 1.0


def test_blocking_key_pads_short_names():
    assert blocking_key("AB", "CA") == "AB__|CA"


def test_identical_name_and_address_clears_the_threshold():
    left = candidate("r1", "ACME WIDGETS", address="1 MAIN ST")
    right = candidate("r2", "ACME WIDGETS", address="1 MAIN ST")
    assert score_pair(left, right).score >= 0.80


def test_score_carries_the_reasons_for_the_match():
    left = candidate("r1", "ACME WIDGETS", phone="+14155550123")
    right = candidate("r2", "ACME WIDGETS", phone="+14155550123")
    reasons = score_pair(left, right).reasons
    assert "name_exact" in reasons
    assert "phone_exact" in reasons


def test_different_companies_stay_in_separate_clusters():
    records = [
        candidate("r1", "ACME WIDGETS"),
        candidate("r2", "NORTHWIND TRADERS", state="NY"),
    ]
    assignments = cluster(records)
    assert assignments["r1"] != assignments["r2"]


def test_matching_records_collapse_into_one_cluster():
    records = [
        candidate("r1", "ACME WIDGETS", phone="+14155550123"),
        candidate("r2", "ACME WIDGETS", phone="+14155550123"),
    ]
    assignments = cluster(records)
    assert assignments["r1"] == assignments["r2"]


def test_clusters_are_transitive_across_a_shared_link():
    # r1 and r2 join on address, r2 and r3 join on phone, but r1 and r3 share
    # only the name and score 0.70, below the threshold. Union-find still puts
    # all three together, which is the behaviour to be aware of when tuning the
    # threshold down.
    records = [
        candidate("r1", "ACME WIDGETS", address="1 MAIN ST"),
        candidate("r2", "ACME WIDGETS", address="1 MAIN ST", phone="+14155550123"),
        candidate("r3", "ACME WIDGETS", phone="+14155550123"),
    ]
    assert score_pair(records[0], records[2]).score < 0.80
    assignments = cluster(records)
    assert len(set(assignments.values())) == 1


def test_blocking_prevents_cross_state_comparison():
    records = [
        candidate("r1", "ACME WIDGETS", state="CA", address="1 MAIN ST"),
        candidate("r2", "ACME WIDGETS", state="NY", address="1 MAIN ST"),
    ]
    assignments = cluster(records)
    assert assignments["r1"] != assignments["r2"]
