# AvoConnect — "My Finances" View (Interactive Prototype)

A clickable, front-end-only prototype of a new **My Finances** area for the
AvoConnect farmer app. It demonstrates the required UX for handling **Bank,
Income, Invoices, Cashflow and Expenses** — including first-class **Invoices**
(which the current production app does not have).

This is a **design/UX prototype**, not production code. It runs entirely in the
browser with no backend, no build step, and no database. All data is in-memory
seed data (`avo-finance-app/data.js`) and resets on refresh.

---

## What it shows

A mobile-first (phone-sized) screen built on AvoConnect's existing visual
language (the same palette and "earth luxe" styling as the production report
form):

- **My Finances hub** — a 5-card grid (Bank · Income · Invoice · Cashflow ·
  Expenses), each card with a live metric and quick-action shortcuts, plus a
  net-cashflow header and a dynamic "insights" strip.
- **Invoices** — Create an invoice through a 4-step flow
  (client → line items → terms → review), with auto OR manual invoice
  numbers and attachments (PO / delivery note). Each invoice opens into a
  detail view.
- **Per-line-item payments** — on an invoice, individual line items can be
  marked paid separately. Status (draft / sent / partial / paid / overdue)
  updates automatically.
- **Income** — log income tied to an invoice (records a payment and
  links back) or as a standalone direct sale that was never invoiced.
- **Expenses** — log expenses against the same categories as the existing
  `ProductionExpenses` model (machinery, wages, fuel, packaging, transport,
  safety, maintenance, raw materials, other…).
- **Bank** — multiple accounts with balances, plus a reconciliation flow:
  imported bank-statement entries are matched against captured income/expenses.
- **Cashflow** — historical money-in-vs-out chart and a forward forecast
  from open invoices, plus a revenue-by-product breakdown.
- **Live state** — creating an invoice, recording a payment, or logging an
  expense immediately updates every relevant total across the app.

Everything is wired: forms submit, state changes, balances move, toasts confirm.
State also persists across page refreshes via localStorage.

---

## How to run it

This app loads modules over HTTP, so it **must be served from a local web
server** — opening `index.html` directly via `file://` will not work.

Pick whichever you have on hand. Run the command from **inside this folder**
(the one containing this README), then open the URL it prints.

### Option A — Python 3 (almost always pre-installed)
```bash
cd avoconnect-myfinances-demo
python3 -m http.server 8000
```
Then open: **http://localhost:8000/avo-finance-app/**

### Option B — Node.js
```bash
cd avoconnect-myfinances-demo
npx serve .
# or:  npx http-server -p 8000
```
Then open the printed URL and navigate to **/avo-finance-app/**.

### Option C — VS Code
Install the **Live Server** extension, right-click `avo-finance-app/index.html` →
**"Open with Live Server."**

> **Best viewed narrow.** It's designed for a phone. On desktop, open your
> browser DevTools device toolbar (Cmd/Ctrl+Shift+M) and pick a phone like
> iPhone 14 / Pixel 7, or just narrow the window.

---

## Project structure

```
avoconnect-myfinances-demo/
├── README.md                          ← you are here
├── avo-finance-app/                   ← the prototype app
│   ├── index.html                     ← ENTRY POINT — serve & open this
│   ├── data.js                        ← in-memory seed data (clients, products,
│   │                                    invoices, income, expenses, bank, statement)
│   ├── app.js                         ← state layer, navigation, views, forms
│   └── styles.css                     ← all app styles (Bootstrap 5 + custom tokens)
```

> **Note:** The `design_system/` folder (adjacent to this directory) contains
> shared Avovision brand tokens and fonts. The vanilla JS app loads Quicksand
> from Google Fonts CDN and defines its palette inline, so `design_system/` is
> not required for this prototype.

`avo-finance-app/styles.css` imports Google Fonts and Bootstrap 5 from CDN.
You'll need internet connectivity on first load for the fonts and Bootstrap CDNs.

---

## Tech notes (for the developer)

- **No build step.** Pure vanilla JavaScript (no React, no framework). Bootstrap 5
  CSS and JS are loaded from CDN in `index.html`.
- **State persistence.** In-memory state is backed by `localStorage` — changes
  survive page refreshes. Use the **"Reset to seed data"** button at the bottom
  of the hub to restore default data.
- **No real API calls.** Everything runs client-side with seed data.
- **Where the real model maps in:** the seed shapes in `avo-finance-app/data.js`
  intentionally mirror the existing Django models (`Client`, the per-product
  `*Sales` models, and `ProductionExpenses`). The **`Invoice`**, **`IncomeEntry`**
  and **`BankAccount`** shapes are the proposed *new* entities — `app.js` is the
  single place that defines how they relate (invoice ⇄ line-item payments ⇄
  income ⇄ bank balance), which is the behaviour to reproduce on the backend.

---

## Purpose

Use this as the **reference spec** for what the My Finances feature needs to do.
It is meant to be run, clicked through, and demoed — the interactions, data
relationships and screen flow are the requirement.
