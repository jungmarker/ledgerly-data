"""Make the raw exports look like a real CRM: duplicates, typos, stale pipeline, missing fields.

Every injected problem is recorded in a truth table so dedupe and data-quality work can be scored.
"""
import copy
from datetime import timedelta

import numpy as np

from .util import IdFactory, days

STATE_NAMES = {"CA": "California", "NY": "New York", "TX": "Texas", "FL": "Florida", "IL": "Illinois",
               "MA": "Massachusetts", "WA": "Washington", "GA": "Georgia", "CO": "Colorado", "NC": "North Carolina",
               "VA": "Virginia", "MD": "Maryland", "PA": "Pennsylvania", "OH": "Ohio", "MN": "Minnesota",
               "AZ": "Arizona", "NJ": "New Jersey", "OR": "Oregon", "MI": "Michigan", "TN": "Tennessee",
               "UT": "Utah", "MO": "Missouri", "WI": "Wisconsin", "IN": "Indiana"}
NICKNAMES = {"Robert": "Bob", "William": "Bill", "Elizabeth": "Liz", "Jennifer": "Jen", "Michael": "Mike",
             "Christopher": "Chris", "Katherine": "Kate", "James": "Jim", "Richard": "Rick", "Daniel": "Dan",
             "Matthew": "Matt", "Joseph": "Joe", "Thomas": "Tom", "Anthony": "Tony", "Patricia": "Pat",
             "Margaret": "Maggie", "Jessica": "Jess", "Samantha": "Sam", "Nicholas": "Nick", "Andrew": "Andy"}


class Messifier:
    def __init__(self, rng: np.random.Generator, ids: IdFactory):
        self.rng, self.ids = rng, ids
        self.account_dupes, self.contact_dupes = [], []

    # ------------------------------------------------------------- string noise
    def _typo(self, s: str) -> str:
        if len(s) < 4:
            return s
        i = int(self.rng.integers(1, len(s) - 2))
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]

    def _name_variant(self, name: str) -> str:
        r = self.rng.random()
        if r < 0.25:
            return name.upper()
        if r < 0.45:
            for a, b in ((" Inc.", ", Inc"), (" LLC", " L.L.C."), (" Corp.", " Corporation"), (" Co.", " Company")):
                if name.endswith(a):
                    return name[: -len(a)] + b
            return name + " Inc"
        if r < 0.65:
            return self._typo(name)
        if r < 0.8:
            return name.split(" ")[0] + (" " + name.split(" ")[1] if len(name.split(" ")) > 1 else "")
        return "The " + name

    def _phone_variant(self, p: str) -> str:
        a, b, c = p[:3], p[4:7], p[8:]
        return self.rng.choice([f"({a}) {b}-{c}", f"{a}.{b}.{c}", f"+1 {a} {b} {c}", f"{a}{b}{c}"])

    # ------------------------------------------------------------- tables
    def accounts(self, accounts, contacts):
        rng = self.rng
        out = []
        for a in accounts:
            r = {k: v for k, v in a.items() if not k.startswith("_")}
            if rng.random() < 0.06:
                r["industry"] = None
            if rng.random() < 0.05:
                r["employee_count"] = None
            if rng.random() < 0.08:
                r["billing_state"] = rng.choice([STATE_NAMES[r["billing_state"]], r["billing_state"].lower()])
            out.append(r)
        by_acct = {}
        for c in contacts:
            by_acct.setdefault(c["account_id"], []).append(c)
        for a in list(out):
            if rng.random() < 0.045:
                d = copy.copy(a)
                d["account_id"] = self.ids.new("account")
                d["account_name"] = self._name_variant(a["account_name"])
                d["website"] = rng.choice([a["website"].replace("www.", "https://"), a["website"].replace("www.", ""), a["website"]])
                d["created_at"] = a["created_at"] + timedelta(days=int(rng.integers(5, 400)))
                d["status"], d["customer_since"], d["csm_id"] = "Prospect", None, None
                if rng.random() < 0.3:
                    d["billing_state"] = STATE_NAMES.get(str(a["billing_state"]).upper(), a["billing_state"])
                out.append(d)
                self.account_dupes.append(dict(duplicate_account_id=d["account_id"], master_account_id=a["account_id"]))
                # Some contacts were created against the duplicate instead of the master
                for c in by_acct.get(a["account_id"], []):
                    if not c["is_primary"] and rng.random() < 0.35:
                        c["account_id"] = d["account_id"]
        return out

    def contacts(self, contacts):
        rng = self.rng
        out = []
        for c in contacts:
            r = dict(c)
            if rng.random() < 0.07:
                r["title"] = None
            if rng.random() < 0.3:
                r["phone"] = self._phone_variant(c["phone"])
            if rng.random() < 0.015:
                r["email"] = rng.choice([c["email"].replace("@", ""), c["email"].split("@")[0] + "@", c["email"] + " "])
            out.append(r)
        for c in list(out):
            if rng.random() < 0.06:
                d = dict(c)
                d["contact_id"] = self.ids.new("contact")
                d["is_primary"], d["lead_id"] = False, None
                d["created_at"] = c["created_at"] + timedelta(days=int(rng.integers(3, 300)))
                kind = rng.random()
                if kind < 0.35:
                    d["first_name"] = NICKNAMES.get(c["first_name"], c["first_name"][:3])
                elif kind < 0.6:
                    d["email"] = c["email"].upper()
                elif kind < 0.8:
                    d["email"] = f"{c['first_name']}.{c['last_name']}{rng.integers(1, 99)}@gmail.com".lower()
                else:
                    d["last_name"] = self._typo(c["last_name"])
                d["phone"] = self._phone_variant(str(c["phone"])[:12]) if str(c["phone"])[3] == "-" else c["phone"]
                out.append(d)
                self.contact_dupes.append(dict(duplicate_contact_id=d["contact_id"], master_contact_id=c["contact_id"]))
        return out

    def leads(self, leads):
        rng = self.rng
        out = [dict(l) for l in leads]
        for l in list(out):
            if rng.random() < 0.05:
                d = dict(l)
                d["lead_id"] = self.ids.new("lead")
                d["email"] = l["email"].upper() if rng.random() < 0.5 else l["email"]
                d["created_at"] = l["created_at"] + timedelta(days=int(rng.integers(1, 200)))
                d.update(status="Open", mql_at=None, converted_at=None, converted_account_id=None,
                         converted_opportunity_id=None)
                out.append(d)
        return out

    def opportunities(self, opps, as_of):
        """Hide truth columns; add stale close dates and missing amounts on early-stage deals."""
        rng = self.rng
        out, truth = [], []
        for o in opps:
            r = {k: v for k, v in o.items() if not k.startswith("_")}
            if not o["is_closed"]:
                truth.append(dict(opportunity_id=o["opportunity_id"], will_win=o.get("_will_win"),
                                  true_close_date=o["_true_close"]))
                if rng.random() < 0.12:  # rep never updated a slipped deal
                    r["close_date"] = as_of - days(rng.integers(5, 90))
                if r["stage"] == "Discovery" and rng.random() < 0.3:
                    r["amount"], r["seats"] = None, None
            out.append(r)
        return out, truth
