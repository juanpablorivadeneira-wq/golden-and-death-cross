"""Tests de agrupación de watchlist: grupos personalizados a nivel de datos."""


def test_create_and_list_groups_in_order(tmp_db):
    assert tmp_db.create_group("FANG+2") is True
    assert tmp_db.create_group("Cripto") is True
    assert tmp_db.list_groups() == ["FANG+2", "Cripto"]


def test_create_duplicate_group_fails(tmp_db):
    tmp_db.create_group("Cripto")
    assert tmp_db.create_group("Cripto") is False
    assert tmp_db.list_groups() == ["Cripto"]


def test_assign_ticker_to_group(tmp_db):
    tmp_db.create_group("FANG+2")
    tmp_db.add_ticker("META")
    assert tmp_db.set_ticker_group("META", "FANG+2") is True
    row = next(r for r in tmp_db.get_watchlist() if r["ticker"] == "META")
    assert row["group_name"] == "FANG+2"


def test_assign_ticker_to_nonexistent_group_fails(tmp_db):
    tmp_db.add_ticker("META")
    assert tmp_db.set_ticker_group("META", "No existe") is False


def test_assign_unknown_ticker_fails(tmp_db):
    tmp_db.create_group("FANG+2")
    assert tmp_db.set_ticker_group("ZZZZ", "FANG+2") is False


def test_unassign_ticker_back_to_ungrouped(tmp_db):
    tmp_db.create_group("FANG+2")
    tmp_db.add_ticker("META")
    tmp_db.set_ticker_group("META", "FANG+2")
    assert tmp_db.set_ticker_group("META", None) is True
    row = next(r for r in tmp_db.get_watchlist() if r["ticker"] == "META")
    assert row["group_name"] is None


def test_rename_group_updates_member_tickers(tmp_db):
    tmp_db.create_group("Cripto")
    tmp_db.add_ticker("BTC-USD")
    tmp_db.set_ticker_group("BTC-USD", "Cripto")
    assert tmp_db.rename_group("Cripto", "Crypto") is True
    assert tmp_db.list_groups() == ["Crypto"]
    row = next(r for r in tmp_db.get_watchlist() if r["ticker"] == "BTC-USD")
    assert row["group_name"] == "Crypto"


def test_rename_to_existing_name_fails(tmp_db):
    tmp_db.create_group("Cripto")
    tmp_db.create_group("FANG+2")
    assert tmp_db.rename_group("Cripto", "FANG+2") is False


def test_delete_group_ungroups_members_instead_of_deleting_tickers(tmp_db):
    tmp_db.create_group("Cripto")
    tmp_db.add_ticker("BTC-USD")
    tmp_db.set_ticker_group("BTC-USD", "Cripto")
    assert tmp_db.delete_group("Cripto") is True
    assert tmp_db.list_groups() == []
    row = next(r for r in tmp_db.get_watchlist() if r["ticker"] == "BTC-USD")
    assert row["group_name"] is None  # el ticker sigue en la watchlist, solo pierde el grupo


def test_delete_nonexistent_group_fails(tmp_db):
    assert tmp_db.delete_group("No existe") is False


def test_move_group_swaps_order_with_neighbor(tmp_db):
    tmp_db.create_group("A")
    tmp_db.create_group("B")
    tmp_db.create_group("C")
    assert tmp_db.list_groups() == ["A", "B", "C"]
    assert tmp_db.move_group("B", "up") is True
    assert tmp_db.list_groups() == ["B", "A", "C"]
    assert tmp_db.move_group("B", "down") is True
    assert tmp_db.list_groups() == ["A", "B", "C"]


def test_move_group_at_edge_is_a_noop(tmp_db):
    tmp_db.create_group("A")
    tmp_db.create_group("B")
    assert tmp_db.move_group("A", "up") is False
    assert tmp_db.list_groups() == ["A", "B"]
    assert tmp_db.move_group("B", "down") is False
    assert tmp_db.list_groups() == ["A", "B"]
