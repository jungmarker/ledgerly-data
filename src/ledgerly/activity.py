"""Customer activity driven by hidden health: weekly product usage, support tickets, invoices."""
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from . import config as C
from .lifecycle import Lifecycle
from .util import IdFactory, add_months, days, random_time

# --- support ticket text --------------------------------------------------------------
AREAS = ("approval workflows", "the close checklist", "bank reconciliation", "the AP inbox", "custom reports",
         "the vendor portal", "spend dashboards", "journal entry imports", "multi-entity consolidation")
TEMPLATES = {
    "How-To": [("How do I set up {area}?", "Hi team, we're trying to configure {area} for our {team} team. Is there a guide or best practice? Thanks."),
               ("Question about {area}", "Can someone walk me through how {area} handles {thing}? I couldn't find it in the help center."),
               ("Training for new users", "We just added {n} new users. Do you have training material for {area}?")],
    "Bug": [("Error {code} when using {area}", "Since this morning we get error {code} whenever we open {area}. It happens for {n} users. Screenshot attached."),
            ("{area} not loading", "{area} has been spinning for 10+ minutes. Tried Chrome and Edge. This is blocking month-end close."),
            ("Numbers don't match in {area}", "Totals in {area} are off by ${amt} compared to the export. Looks like a calculation bug.")],
    "Billing": [("Question about our invoice", "Our latest invoice shows {n} seats but we only have {m} active users. Can you review the charges?"),
                ("Update payment method", "We need to switch our payment method to ACH and update the billing contact to {email}."),
                ("Duplicate charge", "It looks like we were charged twice this month (${amt}). Please refund the duplicate.")],
    "Account Access": [("Locked out of my account", "I'm locked out after the password reset email never arrived. I need access today for close."),
                       ("SSO login failing", "After switching our IdP, SSO fails with error {code} for everyone on the {team} team."),
                       ("Add admin permissions", "Please give {email} admin rights. Our previous admin left the company.")],
    "Integration": [("{integ} sync failing", "Our {integ} sync has failed for {n} days with error {code}. Transactions are not coming through."),
                    ("Help connecting {integ}", "We want to connect {integ} but the authorization keeps timing out. Any guidance?"),
                    ("{integ} duplicates", "The {integ} integration created duplicate vendor records. About {n} duplicates so far.")],
    "Feature Request": [("Feature request: {area}", "It would be great if {area} supported {thing}. This would save our team hours each week."),
                        ("Can you add an export option?", "We'd love a scheduled CSV export from {area} to our data warehouse.")],
    "Cancellation": [("Cancel our subscription", "We've decided not to renew. Please confirm the cancellation process and data export options."),
                     ("Reducing seats at renewal", "We're not getting enough value from {area} and plan to cut seats or cancel at renewal."),
                     ("Considering other options", "Leadership is evaluating alternatives given the issues with {area}. Can we talk about next steps?")],
}
TEAMS = ("AP", "AR", "FP&A", "accounting", "procurement", "treasury")
THINGS = ("multi-currency", "approval delegation", "partial payments", "custom fields", "audit trails", "bulk edits")


class Activity:
    def __init__(self, rng: np.random.Generator, ids: IdFactory, life: Lifecycle):
        self.rng, self.ids, self.life = rng, ids, life
        self.usage, self.tickets, self.ticket_labels, self.invoices = [], [], [], []
        self.health = defaultdict(dict)
        for r in life.health:
            self.health[r["account_id"]][r["month"]] = r["health"]
        self.lines_by_sub = defaultdict(list)
        for ln in life.lines:
            self.lines_by_sub[ln["subscription_id"]].append(ln)
        self.contacts = defaultdict(list)
        for c in life.funnel.contacts:
            self.contacts[c["account_id"]].append(c)

    def h(self, account_id: str, d: date) -> float:
        hs = self.health[account_id]
        return hs.get(date(d.year, d.month, 1), next(iter(hs.values()), 0.55))

    def run(self):
        for sub in self.life.subscriptions:
            end = min(sub["end_date"] or C.AS_OF, C.AS_OF)
            self._usage(sub, end)
            self._tickets(sub, end)
            self._invoices(sub)
        return self

    def seats_on(self, sub_id: str, d: date) -> int:
        return sum(ln["seats"] for ln in self.lines_by_sub[sub_id] if ln["start_date"] <= d <= ln["end_date"])

    # ---------------------------------------------------------------- usage
    def _usage(self, sub, end):
        rng, acct_id = self.rng, sub["account_id"]
        wk = sub["start_date"] - timedelta(days=sub["start_date"].weekday())
        integrations = 0
        onboarding_weeks = int(rng.integers(4, 12))
        i = 0
        while wk <= end:
            seats = self.seats_on(sub["subscription_id"], wk) or self.seats_on(sub["subscription_id"], wk + days(6))
            if seats:
                h = self.h(acct_id, wk)
                ramp = min(1.0, (i + 1) / onboarding_weeks)
                adoption = float(np.clip((0.15 + 0.75 * h) * ramp + rng.normal(0, 0.05), 0.01, 1))
                wau = int(rng.binomial(seats, adoption))
                if rng.random() < 0.02 * h and integrations < 5:
                    integrations += 1
                row = dict(account_id=acct_id, week_start=wk, licensed_seats=seats, weekly_active_users=wau,
                           integrations_connected=integrations)
                for f, rate in zip(C.FEATURES, (0.6, 3.0, 4.0, 40.0)):
                    row[f] = int(rng.poisson(max(wau * rate * (0.4 + h), 0)))
                self.usage.append(row)
                i += 1
            wk += days(7)

    # ---------------------------------------------------------------- support
    def _tickets(self, sub, end):
        rng, acct_id = self.rng, sub["account_id"]
        cats = list(C.TICKET_CATEGORIES)
        base = np.array([C.TICKET_CATEGORIES[c][0] for c in cats])
        m = date(sub["start_date"].year, sub["start_date"].month, 1)
        while m <= end:
            seats = self.seats_on(sub["subscription_id"], m) or self.seats_on(sub["subscription_id"], m + days(27))
            h = self.h(acct_id, m)
            near_churn = sub["end_date"] is not None and 0 <= (sub["end_date"] - m).days <= 75
            lam = 0.04 * max(seats, 1) ** 0.6 * (1.7 - h)
            for _ in range(rng.poisson(lam)):
                w = base.copy()
                w[cats.index("Bug")] *= 1.6 - h
                w[cats.index("Cancellation")] *= 6 if near_churn else (1.5 - h) * 0.5
                cat = cats[rng.choice(len(cats), p=w / w.sum())]
                day = m + days(rng.integers(0, 28))
                if day <= end:
                    self._ticket(acct_id, cat, day, h, seats)
            m = add_months(m, 1)

    def _ticket(self, acct_id, cat, day, h, seats):
        rng = self.rng
        subj, body = TEMPLATES[cat][rng.integers(len(TEMPLATES[cat]))]
        contact = self.contacts[acct_id][rng.integers(len(self.contacts[acct_id]))]
        slots = dict(area=rng.choice(AREAS), team=rng.choice(TEAMS), thing=rng.choice(THINGS), n=int(rng.integers(2, 40)),
                     m=int(rng.integers(1, max(2, seats))), code=f"E{rng.integers(100, 999)}", amt=f"{rng.integers(120, 9800):,}",
                     email=contact["email"], integ=rng.choice(C.INTEGRATIONS))
        prio_w = np.array(C.TICKET_CATEGORIES[cat][1])
        true_prio = ("Low", "Normal", "High", "Urgent")[rng.choice(4, p=prio_w / prio_w.sum())]
        created = random_time(rng, day)
        resolve_hours = rng.lognormal({"Low": 4.0, "Normal": 3.3, "High": 2.6, "Urgent": 1.6}[true_prio], 0.8)
        resolved = created + timedelta(hours=float(resolve_hours))
        csat = int(np.clip(round(rng.normal(2.2 + 2.6 * h - 0.004 * resolve_hours, 0.8)), 1, 5))
        case_id = self.ids.new("case")
        # What the support agent typed: usually right, sometimes wrong or blank (realistic noise)
        r = rng.random()
        agent_cat = cat if r < 0.78 else (None if r < 0.9 else rng.choice([c for c in C.TICKET_CATEGORIES if c != cat]))
        self.tickets.append(dict(case_id=case_id, account_id=acct_id, contact_id=contact["contact_id"],
                                 created_at=created, channel=rng.choice(("Email", "Web Form", "Chat"), p=[0.5, 0.3, 0.2]),
                                 subject=subj.format(**slots), description=body.format(**slots),
                                 priority_requested=rng.choice(("Low", "Normal", "High", "Urgent"), p=[0.15, 0.45, 0.28, 0.12]),
                                 agent_category=agent_cat,
                                 status="Closed" if resolved.date() <= C.AS_OF else "Open",
                                 first_response_minutes=int(rng.lognormal(4.2 if true_prio in ("Low", "Normal") else 3.2, 0.7)),
                                 resolved_at=resolved if resolved.date() <= C.AS_OF else None,
                                 csat_score=csat if resolved.date() <= C.AS_OF and rng.random() < 0.35 else None))
        self.ticket_labels.append(dict(case_id=case_id, true_category=cat, true_priority=true_prio,
                                       routed_team=C.TICKET_CATEGORIES[cat][2],
                                       churn_signal=cat == "Cancellation" or (cat == "Bug" and h < 0.35)))

    # ---------------------------------------------------------------- billing
    def _invoices(self, sub):
        rng = self.rng
        items = defaultdict(float)
        for ln in self.lines_by_sub[sub["subscription_id"]]:
            if sub["billing_frequency"] == "Annual":
                months = max(1, round((ln["end_date"] - ln["start_date"]).days / 30.4))
                items[ln["start_date"]] += ln["mrr"] * months
            else:
                d = ln["start_date"]
                while d <= ln["end_date"] and d <= C.AS_OF:
                    items[d] += ln["mrr"]
                    d = add_months(d, 1)
        for inv_date, amount in sorted(items.items()):
            if inv_date > C.AS_OF:
                continue
            h = self.h(sub["account_id"], inv_date)
            due = inv_date + days(30)
            pay_days = rng.lognormal(np.log(18 + 40 * (1 - h)), 0.5)
            paid = inv_date + days(pay_days)
            churned_soon = sub["end_date"] is not None and (sub["end_date"] - inv_date).days < 60
            if (churned_soon and rng.random() < 0.35) or paid > C.AS_OF:
                status, paid = ("Written Off" if churned_soon and due + days(120) < C.AS_OF else
                                "Overdue" if due < C.AS_OF else "Open"), None
            else:
                status = "Paid"
            self.invoices.append(dict(invoice_id=self.ids.new("invoice"), subscription_id=sub["subscription_id"],
                                      account_id=sub["account_id"], invoice_date=inv_date, due_date=due,
                                      amount=round(amount, 2), status=status, paid_date=paid))
