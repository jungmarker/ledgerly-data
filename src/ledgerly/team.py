"""Ledgerly's go-to-market team: AEs, CSMs and SDRs with territories and attrition."""
from datetime import date

import numpy as np
from faker import Faker

from .config import AS_OF, START
from .util import IdFactory, days

ROLES = (
    # role, segment, region, headcount at start
    *(("Account Executive", "SMB", r, 2) for r in ("East", "Central", "West")),
    *(("Account Executive", "Mid-Market", r, 2) for r in ("East", "Central", "West")),
    ("Account Executive", "Enterprise", "All", 3),
    ("Customer Success Manager", "SMB", "All", 2),
    ("Customer Success Manager", "Mid-Market", "All", 3),
    ("Customer Success Manager", "Enterprise", "All", 2),
    ("Sales Development Rep", "All", "All", 5),
)


class Team:
    def __init__(self, rng: np.random.Generator, fake: Faker, ids: IdFactory):
        self.rng, self.fake, self.ids = rng, fake, ids
        self.users: list[dict] = []
        for role, seg, region, n in ROLES:
            for _ in range(n):
                self._hire(role, seg, region, START - days(rng.integers(30, 900)))
        self._simulate_attrition()

    def _hire(self, role, seg, region, hired):
        first, last = self.fake.first_name(), self.fake.last_name()
        u = dict(user_id=self.ids.new("user"), full_name=f"{first} {last}",
                 email=f"{first}.{last}@ledgerly.io".lower(), role=role, segment=seg, region=region,
                 hire_date=hired, termination_date=None)
        self.users.append(u)
        return u

    def _simulate_attrition(self):
        """~18%/yr rep attrition; each departure is backfilled 30-75 days later."""
        d = START
        while d <= AS_OF:
            for u in [u for u in self.users if u["termination_date"] is None and u["hire_date"] <= d]:
                if self.rng.random() < 0.18 / 12:
                    u["termination_date"] = d
                    self._hire(u["role"], u["segment"], u["region"], d + days(self.rng.integers(30, 75)))
            d += days(30)

    def active(self, role: str, seg: str, region: str, on: date) -> list[dict]:
        ok = [u for u in self.users if u["role"] == role and u["hire_date"] <= on
              and (u["termination_date"] is None or u["termination_date"] > on)
              and u["segment"] in (seg, "All") and u["region"] in (region, "All")]
        if not ok:  # coverage gap: fall back to any active rep in the role
            ok = [u for u in self.users if u["role"] == role and u["hire_date"] <= on
                  and (u["termination_date"] is None or u["termination_date"] > on)]
        return ok

    def pick(self, role: str, seg: str, region: str, on: date) -> str:
        pool = self.active(role, seg, region, on)
        return pool[self.rng.integers(len(pool))]["user_id"]
