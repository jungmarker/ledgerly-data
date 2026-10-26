"""Top of funnel: leads → MQL → opportunity → closed won/lost, plus accounts and contacts.

Every company that reaches the opportunity stage becomes an Account. Each account has a
hidden `fit` score (0-1) that drives win rate here and health/churn later; it is exported
only to the truth tables.
"""
from datetime import date

import numpy as np
from faker import Faker

from . import config as C
from .team import Team
from .util import IdFactory, days, month_starts, random_time

LEAD_TITLES = ("Controller", "CFO", "VP of Finance", "Director of Finance", "AP Manager", "Accounting Manager",
               "FP&A Manager", "Finance Operations Manager", "Revenue Accountant", "Head of Finance",
               "Operations Manager", "Senior Accountant")
EXTRA_CONTACT_TITLES = ("Staff Accountant", "IT Director", "Procurement Manager", "AP Specialist",
                        "Systems Administrator", "COO", "Payroll Manager", "Finance Analyst")
COMPANY_SUFFIX = ("Inc.", "LLC", "Corp.", "Co.", "Group", "Holdings", "")


class Funnel:
    def __init__(self, rng: np.random.Generator, fake: Faker, ids: IdFactory, team: Team):
        self.rng, self.fake, self.ids, self.team = rng, fake, ids, team
        self.leads, self.accounts, self.contacts = [], [], []
        self.opps, self.stage_history = [], []

    # ------------------------------------------------------------------ helpers
    def _company(self):
        base = self.fake.company().replace(",", "").split(" ")[0:2]
        name = " ".join(base)
        suffix = COMPANY_SUFFIX[self.rng.integers(len(COMPANY_SUFFIX))]
        domain = "".join(ch for ch in name.lower() if ch.isalnum()) + self.rng.choice([".com", ".com", ".io", ".co"])
        return (f"{name} {suffix}".strip(), domain)

    def _segment(self):
        names, w = zip(*C.SEGMENT_MIX.items())
        return names[self.rng.choice(len(names), p=np.array(w))]

    def _person(self, domain, title):
        first, last = self.fake.first_name(), self.fake.last_name()
        return dict(first_name=first, last_name=last, title=title, email=f"{first[0]}{last}@{domain}".lower(),
                    phone=self.fake.numerify("###-###-####"))

    # ------------------------------------------------------------------ main loop
    def run(self):
        months = month_starts(C.START, C.AS_OF)
        srcs = list(C.LEAD_SOURCES)
        src_share = np.array([C.LEAD_SOURCES[s][0] for s in srcs])
        for t, m in enumerate(months):
            lam = C.BASE_MONTHLY_LEADS * (1 + C.MONTHLY_LEAD_GROWTH) ** t * C.SEASONALITY[m.month - 1]
            for _ in range(self.rng.poisson(lam)):
                created = m + days(self.rng.integers(0, 28))
                if created > C.AS_OF:
                    continue
                self._lead(created, srcs[self.rng.choice(len(srcs), p=src_share / src_share.sum())])
        return self

    def _lead(self, created: date, source: str):
        rng = self.rng
        name, domain = self._company()
        seg = self._segment()
        state = rng.choice(C.STATES)
        region = C.REGION_BY_STATE[state]
        person = self._person(domain, rng.choice(LEAD_TITLES))
        fit = float(np.clip(rng.beta(2.6, 2.2) + (0.08 if "Referral" in source else 0), 0, 1))
        lead = dict(lead_id=self.ids.new("lead"), created_at=random_time(rng, created), **person, company=name,
                    website=f"www.{domain}", state=state, employee_count=int(rng.integers(*C.SEGMENTS[seg].employees)),
                    lead_source=source, utm_campaign=self._campaign(source, created), status="Open",
                    owner_id=self.team.pick("Sales Development Rep", "All", "All", created),
                    mql_at=None, converted_at=None, converted_account_id=None, converted_opportunity_id=None)
        self.leads.append(lead)

        mql_rate = C.LEAD_SOURCES[source][1]
        if rng.random() > mql_rate:
            lead["status"] = "Disqualified" if rng.random() < 0.6 else "Open"
            return
        mql_day = created + days(rng.integers(0, 10))
        if mql_day > C.AS_OF:
            return
        lead["status"], lead["mql_at"] = "MQL", random_time(rng, mql_day)
        if rng.random() > 0.22 + 0.25 * fit:
            lead["status"] = "Recycled" if rng.random() < 0.5 else "MQL"
            return
        conv_day = mql_day + days(rng.integers(2, 21))
        if conv_day > C.AS_OF:
            return
        acct = self._account(name, domain, seg, state, region, fit, lead, conv_day)
        opp = self._new_business(acct, source, conv_day, fit)
        lead.update(status="Converted", converted_at=random_time(rng, conv_day),
                    converted_account_id=acct["account_id"], converted_opportunity_id=opp["opportunity_id"])

    def _campaign(self, source, d):
        q = f"{d.year}Q{(d.month - 1) // 3 + 1}"
        return {"Paid Search": f"gs_{q}_brand_nonbrand", "Paid Social": f"li_{q}_cfo_persona",
                "Webinar": f"webinar_{q}_close_faster", "Events": f"event_{q}_field",
                "Outbound": f"sdr_{q}_sequence"}.get(source)

    def _account(self, name, domain, seg, state, region, fit, lead, d):
        rng = self.rng
        acct = dict(account_id=self.ids.new("account"), account_name=name, website=f"www.{domain}",
                    industry=rng.choice(C.INDUSTRIES), employee_count=lead["employee_count"], segment=seg,
                    billing_state=state, billing_country="United States", region=region,
                    owner_id=self.team.pick("Account Executive", seg, region, d),
                    csm_id=None, created_at=random_time(rng, d), lead_source=lead["lead_source"],
                    customer_since=None, status="Prospect", _fit=fit)
        self.accounts.append(acct)
        n_contacts = {"SMB": (1, 3), "Mid-Market": (2, 6), "Enterprise": (4, 12)}[seg]
        self.contacts.append(dict(contact_id=self.ids.new("contact"), account_id=acct["account_id"],
                                  **{k: lead[k] for k in ("first_name", "last_name", "title", "email", "phone")},
                                  created_at=acct["created_at"], lead_id=lead["lead_id"], is_primary=True))
        for _ in range(rng.integers(*n_contacts)):
            p = self._person(domain, rng.choice(EXTRA_CONTACT_TITLES + LEAD_TITLES))
            self.contacts.append(dict(contact_id=self.ids.new("contact"), account_id=acct["account_id"], **p,
                                      created_at=random_time(rng, d + days(rng.integers(0, 60))),
                                      lead_id=None, is_primary=False))
        return acct

    # ------------------------------------------------------------------ opportunities
    def price(self, seg_name, plan, seats, discount):
        return round(seats * C.PLAN_PRICE[plan] * 12 * (1 - discount), 2)

    def _new_business(self, acct, source, d, fit):
        rng, seg = self.rng, C.SEGMENTS[acct["segment"]]
        plan = seg.plans[rng.choice(len(seg.plans), p=np.array(seg.plan_weights))]
        seats = int(np.clip(rng.lognormal(np.log(np.mean(seg.seats)), 0.5), *seg.seats))
        discount = round(float(rng.uniform(0, seg.max_discount)), 3)
        p_win = float(np.clip(seg.win_rate * C.LEAD_SOURCES[source][2] * (0.45 + 1.2 * fit), 0.03, 0.75))
        won = rng.random() < p_win
        cycle = max(5, int(rng.lognormal(np.log(seg.cycle_days_median), 0.45)))
        return self.opportunity(acct, "New Business", d, cycle, won, plan, seats, discount, acct["owner_id"])

    def opportunity(self, acct, opp_type, created: date, cycle: int, won: bool, plan, seats, discount, owner_id,
                    lost_stage=None):
        """Create an opportunity with stage history; leave it open if it hasn't closed by AS_OF."""
        rng = self.rng
        close = created + days(cycle)
        last_stage = len(C.STAGES) - 1 if won else (lost_stage if lost_stage is not None
                                                     else int(rng.choice(4, p=[0.35, 0.3, 0.2, 0.15])))
        stage_days = np.sort(rng.uniform(0, cycle, last_stage)).tolist()
        opp = dict(opportunity_id=self.ids.new("opportunity"), account_id=acct["account_id"],
                   opportunity_name=f"{acct['account_name']} - {opp_type} {created.year}",
                   type=opp_type, owner_id=owner_id, created_at=random_time(rng, created), plan=plan,
                   seats=seats, discount=discount, amount=self.price(acct["segment"], plan, seats, discount),
                   close_date=close, stage=None, is_closed=False, is_won=False, loss_reason=None,
                   forecast_category=None, lead_source=acct["lead_source"])
        history = [(C.STAGES[0], created)] + [(C.STAGES[i + 1], created + days(stage_days[i]))
                                              for i in range(last_stage)]
        for stage, when in history:
            if when <= C.AS_OF:
                self.stage_history.append(dict(opportunity_id=opp["opportunity_id"], stage=stage,
                                               entered_at=random_time(rng, when)))
                opp["stage"] = stage
        if close <= C.AS_OF:
            final = "Closed Won" if won else "Closed Lost"
            self.stage_history.append(dict(opportunity_id=opp["opportunity_id"], stage=final,
                                           entered_at=random_time(rng, close)))
            opp.update(stage=final, is_closed=True, is_won=won, forecast_category="Closed" if won else "Omitted",
                       loss_reason=None if won else rng.choice(C.LOSS_REASONS))
        else:
            p = C.STAGE_PROBABILITY[opp["stage"]]
            opp["forecast_category"] = "Commit" if p >= 0.75 else "Best Case" if p >= 0.5 else "Pipeline"
            opp["_will_win"] = won  # ground truth for forecast back-testing
        opp["_true_close"] = close
        self.opps.append(opp)
        return opp
