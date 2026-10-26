# Data Dictionary

Snapshot date: **2026-09-30**. All money is in USD. IDs are Salesforce-style 18-character strings with object prefixes (001 account, 003 contact, 006 opportunity, 00Q lead, 005 user, 500 case).

## raw.leads
| Column | Description |
|---|---|
| lead_id | Lead ID |
| created_at | When the lead entered the CRM |
| first_name, last_name, title, email, phone | Person |
| company, website, state, employee_count | Company as entered on the form |
| lead_source | Organic Search, Paid Search, Paid Social, Webinar, Events, Partner Referral, Customer Referral, Outbound |
| utm_campaign | Campaign tag (null for organic/referral) |
| status | Open, Disqualified, MQL, Recycled, Converted |
| owner_id | SDR (→ users) |
| mql_at, converted_at | Funnel timestamps |
| converted_account_id, converted_opportunity_id | Set when converted |

## raw.accounts
| Column | Description |
|---|---|
| account_id | Account ID (**duplicates exist**; see truth.account_duplicates) |
| account_name, website | Name and domain (variants on duplicates) |
| industry | 12 industries; ~6% null |
| employee_count | ~5% null |
| segment | SMB (10–99 employees), Mid-Market (100–999), Enterprise (1000+) |
| billing_state | Mostly 2-letter codes; ~8% full names or lower case |
| billing_country, region | Region = East / Central / West sales territory |
| owner_id, csm_id | AE and CSM (→ users) |
| created_at | Account creation |
| lead_source | Source of the original lead |
| customer_since | First subscription start date |
| status | Prospect, Customer, Churned |

## raw.contacts
| Column | Description |
|---|---|
| contact_id, account_id | Contact and account (some attached to a duplicate account) |
| first_name, last_name, title, email, phone | Person; phone formats vary, ~1.5% invalid emails |
| created_at | Creation timestamp |
| lead_id | Converted lead, for primary contacts |
| is_primary | Original buyer |

## raw.opportunities
| Column | Description |
|---|---|
| opportunity_id, account_id, opportunity_name | IDs and name |
| type | New Business, Expansion, Renewal |
| owner_id | AE (new/expansion) or CSM (renewal) |
| created_at, close_date | close_date may be stale (in the past) for ~12% of open deals |
| plan, seats, discount, amount | amount = annualized contract value; ~30% null in Discovery |
| stage | Discovery → Demo → Proposal → Negotiation → Closed Won / Closed Lost |
| is_closed, is_won, loss_reason | Outcome |
| forecast_category | Pipeline / Best Case / Commit (open), Closed / Omitted (closed) |
| lead_source | Source of the account's original lead |

## raw.opportunity_stage_history
One row per stage entered: `opportunity_id, stage, entered_at`.

## raw.subscriptions
| Column | Description |
|---|---|
| subscription_id, account_id | One subscription per customer |
| start_date, end_date | end_date set on cancellation |
| billing_frequency | Annual or Monthly |
| status, cancel_reason | Active / Cancelled |

## raw.subscription_lines
Source of truth for MRR/ARR. A line is active on a date if `start_date <= date <= end_date`.

| Column | Description |
|---|---|
| line_id, subscription_id, account_id | IDs |
| start_date, end_date | Line period (expansions co-term to the renewal date) |
| plan, seats, unit_price_monthly, mrr | Pricing (mrr = seats × unit price) |
| change_type | New, Expansion, Renewal (seat changes at renewal = expansion or contraction) |
| opportunity_id | Opportunity that created the line |

## raw.invoices
`invoice_id, subscription_id, account_id, invoice_date, due_date, amount, status (Paid/Open/Overdue/Written Off), paid_date`

## raw.product_usage_weekly
`account_id, week_start, licensed_seats, weekly_active_users, integrations_connected, reports_created, automations_run, approvals_processed, api_calls`

## raw.support_tickets
| Column | Description |
|---|---|
| case_id, account_id, contact_id | IDs |
| created_at, channel | Email, Web Form, Chat |
| subject, description | Free text written by the customer |
| priority_requested | Priority the customer picked (not reliable) |
| agent_category | Category the support agent entered: ~78% correct, ~12% blank, ~10% wrong |
| status, first_response_minutes, resolved_at | Handling |
| csat_score | 1–5, ~35% response rate |

## raw.users
`user_id, full_name, email, role (Account Executive / Customer Success Manager / Sales Development Rep), segment, region, hire_date, termination_date`

## truth.*
| Table | Columns |
|---|---|
| account_fit | account_id, fit (0–1, drives win rate and baseline health) |
| account_health_monthly | account_id, month, health (0–1) |
| churn_events | account_id, churn_date, reason, health_at_churn |
| account_duplicates | duplicate_account_id → master_account_id |
| contact_duplicates | duplicate_contact_id → master_contact_id |
| ticket_labels | case_id, true_category, true_priority, routed_team, churn_signal |
| open_opportunity_outcomes | opportunity_id, will_win, true_close_date |
