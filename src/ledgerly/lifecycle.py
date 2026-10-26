"""Post-sale lifecycle: subscriptions, mid-term expansions, renewals, contractions and churn.

Each customer carries a hidden monthly `health` score (0-1). It mean-reverts toward a level
set by account fit, takes occasional shocks (champion leaves, bad rollout), and drives
expansion, contraction and churn. Health is exported only in truth tables so analytics
projects can be back-tested against it.
"""
import math
from datetime import date

import numpy as np

from . import config as C
from .funnel import Funnel
from .util import IdFactory, add_months, days, month_starts


class Lifecycle:
    def __init__(self, rng: np.random.Generator, ids: IdFactory, funnel: Funnel):
        self.rng, self.ids, self.funnel = rng, ids, funnel
        self.subscriptions, self.lines = [], []
        self.health, self.churn_events = [], []

    def run(self):
        accounts = {a["account_id"]: a for a in self.funnel.accounts}
        won = [o for o in self.funnel.opps if o["type"] == "New Business" and o["is_won"]]
        for opp in sorted(won, key=lambda o: o["close_date"]):
            self._customer(accounts[opp["account_id"]], opp)
        return self

    def _customer(self, acct, opp):
        rng, seg = self.rng, C.SEGMENTS[acct["segment"]]
        start = opp["close_date"] + days(rng.integers(0, 15))
        if start > C.AS_OF:
            return
        billing = "Annual" if rng.random() < seg.annual_billing_share else "Monthly"
        sub = dict(subscription_id=self.ids.new("subscription"), account_id=acct["account_id"], start_date=start,
                   billing_frequency=billing, status="Active", end_date=None, cancel_reason=None)
        self.subscriptions.append(sub)
        acct.update(customer_since=start, status="Customer",
                    csm_id=self.funnel.team.pick("Customer Success Manager", acct["segment"], "All", start))

        plan, seats, discount = opp["plan"], opp["seats"], opp["discount"]
        unit = C.PLAN_PRICE[plan] * (1 - discount)
        term_start, term_end = start, add_months(start, 12) - days(1)
        self._line(sub, term_start, term_end, plan, seats, unit, "New", opp["opportunity_id"])

        target = 0.25 + 0.6 * acct["_fit"]
        h = float(np.clip(target + rng.normal(0, 0.08), 0, 1))
        monthly_cancel = 1 - (1 - seg.churn_base) ** (1 / 12)
        for m in month_starts(start, C.AS_OF)[1:]:
            h = float(np.clip(0.85 * h + 0.15 * target + rng.normal(0, 0.05)
                              - (0.25 if rng.random() < 0.03 else 0), 0, 1))
            self.health.append(dict(account_id=acct["account_id"], month=m, health=round(h, 3)))
            churn_mult = math.exp(-3 * (h - 0.55))

            # Monthly-billed customers can cancel at any month boundary
            if billing == "Monthly" and m < term_end and rng.random() < monthly_cancel * churn_mult * 0.5:
                self._churn(acct, sub, m - days(1), h, term_end_cut=True)
                return

            # Mid-term expansion (more likely for healthy Mid-Market/Enterprise)
            seg_mult = {"SMB": 0.6, "Mid-Market": 1.4, "Enterprise": 1.8}[acct["segment"]]
            if m < term_end and rng.random() < 0.07 * h ** 2 * seg_mult:
                add = max(1, int(seats * rng.uniform(0.08, 0.35)))
                created = max(start, m - days(rng.integers(20, 50)))
                eopp = self.funnel.opportunity(acct, "Expansion", created, (m - created).days,
                                               won=rng.random() < 0.75, plan=plan, seats=add, discount=discount,
                                               owner_id=acct["owner_id"])
                if eopp["is_won"]:
                    self._line(sub, m, term_end, plan, add, unit, "Expansion", eopp["opportunity_id"])
                    seats += add

            # Renewal at term end
            if term_end < m:
                p_churn = min(0.95, seg.churn_base * churn_mult)
                churned = rng.random() < p_churn
                new_seats, new_plan = seats, plan
                if not churned:
                    if h < 0.4:
                        new_seats = max(1, int(seats * rng.uniform(0.65, 0.95)))
                    elif h > 0.6:
                        new_seats = int(seats * rng.uniform(1.0, 1.25))
                    if plan == "Starter" and h > 0.65 and rng.random() < 0.25:
                        new_plan = "Growth"
                renew_created = term_end - days(90)
                ropp = self.funnel.opportunity(acct, "Renewal", renew_created, 91, won=not churned,
                                               plan=new_plan, seats=new_seats, discount=discount,
                                               owner_id=acct["csm_id"], lost_stage=3 if churned else None)
                if churned:
                    self._churn(acct, sub, term_end, h)
                    return
                if new_plan != plan:
                    unit = C.PLAN_PRICE[new_plan] * (1 - discount)
                else:
                    unit = unit * (1 + rng.uniform(0.0, 0.06))  # annual price uplift
                plan, seats = new_plan, new_seats
                term_start, term_end = term_end + days(1), add_months(term_end + days(1), 12) - days(1)
                self._line(sub, term_start, term_end, plan, seats, unit, "Renewal", ropp["opportunity_id"])

        # Still active at AS_OF: renewal opp is open once we're inside the 90-day renewal window
        if term_end > C.AS_OF and term_end - days(90) <= C.AS_OF:
            p_churn = min(0.95, C.SEGMENTS[acct["segment"]].churn_base * math.exp(-3 * (h - 0.55)))
            self.funnel.opportunity(acct, "Renewal", term_end - days(90), 91, won=self.rng.random() > p_churn,
                                    plan=plan, seats=seats, discount=discount, owner_id=acct["csm_id"])

    def _line(self, sub, start, end, plan, seats, unit, change_type, opp_id):
        self.lines.append(dict(line_id=f"SL-{len(self.lines) + 1:06d}", subscription_id=sub["subscription_id"],
                               account_id=sub["account_id"], start_date=start, end_date=end, plan=plan,
                               seats=int(seats), unit_price_monthly=round(unit, 2),
                               mrr=round(unit * seats, 2), change_type=change_type, opportunity_id=opp_id))

    def _churn(self, acct, sub, when: date, h, term_end_cut=False):
        w = np.array([0.2, 0.3 if h < 0.4 else 0.15, 0.2, 0.08, 0.12, 0.25 if h < 0.4 else 0.1])
        reason = str(self.rng.choice(("Budget", "Low Adoption", "Switched to Competitor", "Acquired/Closed",
                                      "Champion Left", "Missing Features"), p=w / w.sum()))
        sub.update(status="Cancelled", end_date=when, cancel_reason=reason)
        acct["status"] = "Churned"
        if term_end_cut:  # monthly cancel: truncate the open line(s)
            for ln in self.lines:
                if ln["subscription_id"] == sub["subscription_id"] and ln["end_date"] > when:
                    ln["end_date"] = when
        self.churn_events.append(dict(account_id=acct["account_id"], churn_date=when, reason=reason,
                                      health_at_churn=round(h, 3)))
