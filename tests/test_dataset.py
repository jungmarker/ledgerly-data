"""Invariants the generated data must satisfy (run: pytest)."""
import pandas as pd
import pytest

from ledgerly import config as C
from ledgerly.generate import build


@pytest.fixture(scope="session")
def data():
    return build(seed=7)


@pytest.fixture(scope="session")
def raw(data):
    return data["raw"]


@pytest.fixture(scope="session")
def truth(data):
    return data["truth"]


@pytest.mark.parametrize("table,key", [("accounts", "account_id"), ("contacts", "contact_id"), ("leads", "lead_id"),
                                       ("opportunities", "opportunity_id"), ("subscriptions", "subscription_id"),
                                       ("invoices", "invoice_id"), ("support_tickets", "case_id"), ("users", "user_id")])
def test_primary_keys_unique(raw, table, key):
    assert raw[table][key].is_unique and raw[table][key].notna().all()


@pytest.mark.parametrize("child,col,parent,pkey", [
    ("contacts", "account_id", "accounts", "account_id"), ("opportunities", "account_id", "accounts", "account_id"),
    ("opportunities", "owner_id", "users", "user_id"), ("subscriptions", "account_id", "accounts", "account_id"),
    ("subscription_lines", "subscription_id", "subscriptions", "subscription_id"),
    ("invoices", "subscription_id", "subscriptions", "subscription_id"),
    ("support_tickets", "contact_id", "contacts", "contact_id"),
    ("opportunity_stage_history", "opportunity_id", "opportunities", "opportunity_id"),
])
def test_foreign_keys(raw, child, col, parent, pkey):
    vals = raw[child][col].dropna()
    assert vals.isin(raw[parent][pkey]).all(), f"{child}.{col} has orphans"


def test_subscription_lines_sane(raw):
    ln = raw["subscription_lines"]
    assert (ln["end_date"] >= ln["start_date"]).all()
    assert (ln["mrr"] > 0).all() and (ln["seats"] > 0).all()
    assert set(ln["change_type"]) <= {"New", "Expansion", "Renewal"}


def test_every_subscription_comes_from_won_deal(raw):
    nb = raw["opportunities"].query("type == 'New Business' and is_won")
    new_lines = raw["subscription_lines"].query("change_type == 'New'")
    assert new_lines["opportunity_id"].isin(nb["opportunity_id"]).all()
    assert len(raw["subscriptions"]) == len(new_lines)


def test_closed_deals_are_in_the_past(raw):
    closed = raw["opportunities"].query("is_closed")
    assert (pd.to_datetime(closed["close_date"]).dt.date <= C.AS_OF).all()


def test_usage_bounded_by_seats(raw):
    u = raw["product_usage_weekly"]
    assert (u["weekly_active_users"] <= u["licensed_seats"]).all()


def test_churned_accounts_have_cancelled_subscription(raw, truth):
    churned = set(truth["churn_events"]["account_id"])
    subs = raw["subscriptions"].set_index("account_id")
    assert (subs.loc[list(churned), "status"] == "Cancelled").all()


def test_truth_tables_reference_raw(raw, truth):
    assert truth["account_duplicates"]["master_account_id"].isin(raw["accounts"]["account_id"]).all()
    assert truth["account_duplicates"]["duplicate_account_id"].isin(raw["accounts"]["account_id"]).all()
    assert truth["contact_duplicates"]["duplicate_contact_id"].isin(raw["contacts"]["contact_id"]).all()
    assert len(truth["ticket_labels"]) == len(raw["support_tickets"])


def test_business_metrics_are_realistic(raw):
    """Guardrails so tuning changes don't produce an implausible company."""
    ln = raw["subscription_lines"]
    active = ln[(ln.start_date <= C.AS_OF) & (ln.end_date >= C.AS_OF)]
    arr = active["mrr"].sum() * 12
    assert 10e6 < arr < 120e6
    nb = raw["opportunities"].query("type == 'New Business' and is_closed")
    assert 0.15 < nb["is_won"].mean() < 0.45


def test_deterministic():
    a, b = build(seed=11)["raw"]["opportunities"], build(seed=11)["raw"]["opportunities"]
    pd.testing.assert_frame_equal(a, b)


def test_active_subscriptions_have_revenue_on_snapshot(raw):
    """Every Active subscription must have a contract line covering the snapshot date
    (regression: renewals due in the final month were never processed and looked like churn)."""
    ln = raw["subscription_lines"]
    covered = set(ln[(ln.start_date <= C.AS_OF) & (ln.end_date >= C.AS_OF)]["subscription_id"])
    active = raw["subscriptions"].query("status == 'Active' and start_date <= @C.AS_OF")
    assert set(active["subscription_id"]) <= covered
