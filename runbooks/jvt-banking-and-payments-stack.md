# JVT Banking And Payments Stack

As of April 14, 2026, this is the recommended JVT Technologies finance stack for the first live service phase.

## First Principle

Keep the first stack simple, low-cost, and professional.

Do not buy a pile of back-office tools before:

- the entity is in place
- the bank account exists
- the payment processor exists
- the first paid invoices can actually be collected

## Hard Prerequisite

Before any real business banking setup, JVT needs:

- the legal business entity name
- formation documents
- EIN confirmation
- beneficial owner and operator identity documents

If that is not done yet, that is the first blocker.

## Recommended Starting Stack

### Banking: Mercury

Why this is the best first default:

- free base business banking
- no monthly fee on the core account
- no account minimums
- no overdraft fees
- free ACH
- free domestic wires
- works well for a U.S. registered service business

What Mercury currently requires:

- U.S. entity formation
- EIN document
- government ID for the operator
- owner information for 25%+ owners
- principal business address

Mercury's current public pricing page shows:

- a free core account
- a paid Plus tier
- a paid Pro tier

For JVT, the core free account is the right starting point unless there is a clear need for the paid controls.

## Good Alternative

### Relay

Relay is a good second choice if JVT wants more envelope-style operational accounts and spend segregation later.

I would still start with Mercury unless Relay’s workflow becomes clearly better for how you want to manage cash.

## Payments: Stripe

This should be the primary collection path.

Why:

- no-code invoices
- hosted invoice page
- ACH and card support
- payment links if needed later
- easy branding
- good path for both one-off service invoices and future recurring support retainers

Recommended JVT default:

- send Stripe-hosted invoices
- prefer ACH for larger invoices
- allow card for convenience
- do not add surcharges in the early phase

Stripe's public pricing currently shows standard online card pricing and ACH pricing, and Stripe Invoicing has its own add-on pricing on top of payment processing. For JVT, the practical takeaway is simple:

- ACH should be the preferred default for larger pilot invoices
- card payments should stay available for convenience
- Stripe-hosted invoices are the easiest first collection path

## Accounting / Books

### Cheapest clean path: Wave Starter

Use this if the goal is minimum cost and simple early books.

Good for:

- early invoices
- light bookkeeping
- basic reporting
- first paid client phase

### Better accountant-friendly path: QuickBooks Online Essentials

Use this when JVT has enough real activity that accounts receivable, accounts payable, and reconciliations are getting annoying.

Good for:

- service businesses
- invoice tracking
- reconciliations
- collaborating with a future bookkeeper or accountant

## Optional Later Add-On

### Wise Business

Do not add this on day one.

Add it later only if JVT begins doing:

- international client payments
- multi-currency work
- contractor payouts outside the U.S.

## Recommended Actual Stack For JVT Right Now

### Cheapest sane stack

- Mercury for banking
- Stripe for invoices and payment collection
- Wave Starter for bookkeeping
- Apple custom email domain for business email identity

### Best “grown-up but still lean” stack

- Mercury for banking
- Stripe for invoices and payment collection
- QuickBooks Online Essentials for accounting

My recommendation for JVT:

- start with the cheapest sane stack now
- move to QuickBooks once there are enough paid invoices that monthly reconciliation matters

## Payment Flow

1. lead replies or demo is booked
2. fit call happens
3. scoped proposal and engagement letter are sent
4. deposit invoice is sent through Stripe
5. client pays by ACH or card
6. Stripe pays out to Mercury
7. payment is recorded in Wave or QuickBooks
8. work starts after signed scope and deposit
9. final invoice or recurring support invoice is sent through Stripe

## Recommended Invoice Policy

For early JVT services:

- Discovery or advisory sessions: due on receipt
- Fixed-scope pilot work: 50% upfront, 50% on delivery or milestone
- Monthly support: billed upfront each month
- Payment terms: due on receipt or Net 7, not Net 30

## Geographic Scope

JVT does not need to stay local.

The right early-market filter is not geography. It is:

- document-heavy work
- privacy sensitivity
- internal search friction
- teams that can start with a scoped pilot

That means national U.S. outreach is reasonable, as long as it stays curated and human-reviewed instead of mass-blasted.

## Recommended “Do Not Do This Yet” List

- do not use card surcharging yet
- do not offer annual custom enterprise billing terms yet
- do not buy full proposal automation software yet
- do not build custom payment infrastructure
- do not try to automate collections aggressively before the first few clients

## Setup Sequence

### Step 1

Confirm the legal business setup:

- exact legal entity name
- EIN
- formation docs

### Step 2

Open Mercury.

### Step 3

Open Stripe using the real business info.

### Step 4

Connect Stripe payouts to Mercury.

### Step 5

Choose Wave or QuickBooks.

### Step 6

Create one self-test invoice and pay it yourself.

### Step 7

Send the first real client invoice only after the self-test works end to end.

## Official References

- Mercury pricing: https://mercury.com/pricing
- Mercury banking requirements: https://mercury.com/business-banking
- Mercury eligibility: https://support.mercury.com/hc/en-us/articles/28770467511060-Eligibility-and-requirements-for-opening-a-Mercury-account
- Stripe pricing: https://stripe.com/pricing
- Stripe invoicing pricing: https://stripe.com/invoicing/pricing
- Stripe no-code invoicing guide: https://docs.stripe.com/invoicing/no-code-guide
- Wave pricing: https://www.waveapps.com/pricing
- QuickBooks pricing: https://quickbooks.intuit.com/pricing/
- Wise Business pricing: https://wise.com/us/pricing/business/
