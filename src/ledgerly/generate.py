"""Generate the Ledgerly dataset.

    python -m ledgerly.generate --seed 42 --out data

Writes data/raw (what CRM/billing/product/support exports look like), data/truth (hidden ground
truth for scoring models), Parquet copies, and data/ledgerly.duckdb with `raw` and `truth` schemas.
"""
import argparse
import random
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from faker import Faker

from . import config as C
from .activity import Activity
from .funnel import Funnel
from .lifecycle import Lifecycle
from .messy import Messifier
from .team import Team
from .util import IdFactory


def build(seed: int = 42) -> dict[str, dict[str, pd.DataFrame]]:
    rng = np.random.default_rng(seed)
    random.seed(seed)
    fake = Faker("en_US")
    Faker.seed(seed)
    ids = IdFactory(rng)

    team = Team(rng, fake, ids)
    funnel = Funnel(rng, fake, ids, team).run()
    life = Lifecycle(rng, ids, funnel).run()
    act = Activity(rng, ids, life).run()

    mess = Messifier(rng, ids)
    accounts = mess.accounts(funnel.accounts, funnel.contacts)
    contacts = mess.contacts(funnel.contacts)
    leads = mess.leads(funnel.leads)
    opps, opp_truth = mess.opportunities(funnel.opps, C.AS_OF)

    df = pd.DataFrame
    raw = {
        "users": df(team.users),
        "leads": df(leads),
        "accounts": df(accounts),
        "contacts": df(contacts),
        "opportunities": df(opps),
        "opportunity_stage_history": df(funnel.stage_history),
        "subscriptions": df(life.subscriptions),
        "subscription_lines": df(life.lines),
        "invoices": df(act.invoices),
        "product_usage_weekly": df(act.usage),
        "support_tickets": df(act.tickets),
    }
    truth = {
        "account_fit": df([dict(account_id=a["account_id"], fit=round(a["_fit"], 3)) for a in funnel.accounts]),
        "account_health_monthly": df(life.health),
        "churn_events": df(life.churn_events),
        "account_duplicates": df(mess.account_dupes),
        "contact_duplicates": df(mess.contact_dupes),
        "ticket_labels": df(act.ticket_labels),
        "open_opportunity_outcomes": df(opp_truth),
    }
    return {"raw": raw, "truth": truth}


def write(tables: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "ledgerly.duckdb"
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    for schema, group in tables.items():
        (out / schema).mkdir(parents=True, exist_ok=True)
        (out / "parquet" / schema).mkdir(parents=True, exist_ok=True)
        con.execute(f"create schema if not exists {schema}")
        for name, frame in group.items():
            frame.to_csv(out / schema / f"{name}.csv", index=False)
            frame.to_parquet(out / "parquet" / schema / f"{name}.parquet", index=False)
            con.register("tmp", frame)
            con.execute(f"create table {schema}.{name} as select * from tmp")
            con.unregister("tmp")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("data"))
    args = ap.parse_args()
    t0 = time.time()
    tables = build(args.seed)
    write(tables, args.out)
    print(f"Ledgerly dataset (seed {args.seed}, as of {C.AS_OF}) written to {args.out}/ in {time.time() - t0:.0f}s")
    for schema, group in tables.items():
        for name, frame in group.items():
            print(f"  {schema}.{name:28s} {len(frame):>8,} rows")


if __name__ == "__main__":
    main()
