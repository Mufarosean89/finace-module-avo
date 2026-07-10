/* ============================================================
   AvoConnect — My Finances App
   State management, navigation, views, forms, interactions
   ============================================================ */

(function () {
  'use strict';

  const D = FinanceData;
  let currentPage = 'hub';
  let currentInvoiceId = null;
  let invoices = [];
  let incomeEntries = [];
  let expenseEntries = [];
  let accounts = [];
  let transactions = [];
  let statementEntries = [];
  let showReconcile = false;

  // ── Date range filter state ──────────────────────────
  let dateRange = {
    preset: 'this-month',
    startDate: '2026-05-01',
    endDate: '2026-05-31',
  };

  function getDateRangeForPreset(preset) {
    const presets = {
      'this-month':   { startDate: '2026-05-01', endDate: '2026-05-31' },
      'last-month':   { startDate: '2026-04-01', endDate: '2026-04-30' },
      'last-3-months':{ startDate: '2026-03-01', endDate: '2026-05-31' },
      'this-year':    { startDate: '2026-01-01', endDate: '2026-12-31' },
      'all-time':     { startDate: null,         endDate: null },
    };
    return presets[preset] || presets['this-month'];
  }

  function applyDateRange(preset, startDate, endDate) {
    dateRange.preset = preset;
    dateRange.startDate = startDate;
    dateRange.endDate = endDate;
    renderCurrentView();
  }

  function isInDateRange(itemDateStr, startDate, endDate) {
    if (!startDate && !endDate) return true;
    if (!itemDateStr) return false;
    if (startDate && itemDateStr < startDate) return false;
    if (endDate && itemDateStr > endDate) return false;
    return true;
  }

  function filterByDateRange(items, startDate, endDate) {
    if (!startDate && !endDate) return items;
    return items.filter(item => isInDateRange(item.date, startDate, endDate));
  }

  function filterByIssueDate(items, startDate, endDate) {
    if (!startDate && !endDate) return items;
    return items.filter(item => isInDateRange(item.issueDate, startDate, endDate));
  }

  function renderDateRangePicker() {
    const presets = [
      { id: 'this-month',    label: 'This month' },
      { id: 'last-month',    label: 'Last month' },
      { id: 'last-3-months', label: 'Last 3 mo' },
      { id: 'this-year',     label: 'This year' },
      { id: 'all-time',      label: 'All time' },
    ];

    const isCustom = dateRange.preset === 'custom';
    const rangeDesc = !dateRange.startDate && !dateRange.endDate
      ? 'All time'
      : (dateRange.startDate || '…') + ' – ' + (dateRange.endDate || '…');

    return '<div class="dr-filter">' +
      '<div class="dr-filter-presets">' +
        presets.map(p =>
          '<button class="dr-preset ' + (dateRange.preset === p.id ? 'active' : '') + '" ' +
          'onclick="App.setDateRange(\'' + p.id + '\')">' + p.label + '</button>'
        ).join('') +
        '<button class="dr-preset ' + (isCustom ? 'active' : '') + '" ' +
        'onclick="App.setDateRange(\'custom\')">Custom</button>' +
      '</div>' +
      (!isCustom && dateRange.preset !== 'all-time' && dateRange.startDate ?
        '<div class="dr-range-label">' + rangeDesc + '</div>' : '') +
      (isCustom ? '<div class="dr-custom">' +
        '<div class="dr-field"><label class="dr-label">From</label>' +
          '<input type="date" class="form-control dr-input" id="drStart" value="' + (dateRange.startDate || '') + '"></div>' +
        '<div class="dr-sep">→</div>' +
        '<div class="dr-field"><label class="dr-label">To</label>' +
          '<input type="date" class="form-control dr-input" id="drEnd" value="' + (dateRange.endDate || '') + '"></div>' +
        '<button class="btn btn-teal btn-sm dr-apply" onclick="App.applyCustomDateRange()">Apply</button>' +
      '</div>' : '') +
    '</div>';
  }

  // ── localStorage persistence ────────────────────────────
  const STORAGE_KEY = 'avoconnect_finances';

  function saveState() {
    try {
      const data = {
        invoices: invoices,
        incomeEntries: incomeEntries,
        expenseEntries: expenseEntries,
        accounts: accounts,
        transactions: transactions,
        statementEntries: statementEntries,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (e) {
      console.warn('Failed to save state to localStorage:', e);
    }
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const data = JSON.parse(raw);
      if (!data || typeof data !== 'object') return false;
      invoices = data.invoices || [];
      incomeEntries = data.incomeEntries || [];
      expenseEntries = data.expenseEntries || [];
      accounts = data.accounts || [];
      transactions = data.transactions || [];
      statementEntries = data.statementEntries || [];
      return true;
    } catch (e) {
      console.warn('Failed to load state from localStorage:', e);
      return false;
    }
  }

  function resetToSeed() {
    localStorage.removeItem(STORAGE_KEY);
    initState(true);
    saveState();
    renderCurrentView();
    showToast('Reset complete', 'Data restored to seed values');
  }

  // ── Reconcile helpers ──────────────────────────────────
  function pendingStatements() {
    return statementEntries.filter(s => s.status === 'pending');
  }

  function findMatchCandidates(stmt) {
    const pool = stmt.kind === 'in' ? incomeEntries : expenseEntries;
    return pool
      .map(x => ({
        entry: x,
        score: Math.abs((x.amount || 0) - stmt.amount) + Math.abs(new Date(x.date) - new Date(stmt.date)) / 86400000
      }))
      .sort((a, b) => a.score - b.score)
      .slice(0, 3)
      .map(c => c.entry);
  }

  function reconcileMatch(statementId, capturedRef) {
    statementEntries = statementEntries.map(s =>
      s.id === statementId ? { ...s, status: 'matched', matchedTo: capturedRef } : s
    );
    saveState();
    renderBank();
  }

  function dismissStatement(statementId) {
    statementEntries = statementEntries.map(s =>
      s.id === statementId ? { ...s, status: 'dismissed' } : s
    );
    saveState();
    renderBank();
  }

  function captureStatementAsIncome(statementId) {
    const s = statementEntries.find(x => x.id === statementId);
    if (!s) return;
    const newInc = {
      id: 'inc_' + Date.now(),
      date: s.date,
      source: 'standalone', invoiceId: null,
      clientId: null, productId: null,
      amount: s.amount,
      bankAccountId: s.accountId,
      method: 'eft',
      note: s.reference || 'Captured from bank statement',
    };
    incomeEntries.unshift(newInc);
    const acct = accounts.find(a => a.id === s.accountId);
    if (acct) acct.balance += s.amount;
    transactions.unshift({
      id: 't_' + Date.now(), date: s.date, kind: 'in', amount: s.amount,
      accountId: s.accountId,
      label: 'Statement capture — ' + s.label,
      ref: newInc.id,
    });
    statementEntries = statementEntries.map(se =>
      se.id === statementId ? { ...se, status: 'matched', matchedTo: newInc.id } : se
    );
    saveState();
    showToast('Captured as income', D.fmtR(s.amount) + ' logged');
    closeReconcile();
  }

  function captureStatementAsExpense(statementId) {
    const s = statementEntries.find(x => x.id === statementId);
    if (!s) return;
    const newExp = {
      id: 'exp_' + Date.now(),
      date: s.date,
      categoryId: 'other_expenses', amount: s.amount,
      bankAccountId: s.accountId,
      vendor: s.reference || 'Statement entry',
      note: 'Captured from bank statement',
    };
    expenseEntries.unshift(newExp);
    const acct = accounts.find(a => a.id === s.accountId);
    if (acct) acct.balance -= s.amount;
    transactions.unshift({
      id: 't_' + Date.now(), date: s.date, kind: 'out', amount: s.amount,
      accountId: s.accountId,
      label: 'Statement capture — ' + s.label,
      ref: newExp.id,
    });
    statementEntries = statementEntries.map(se =>
      se.id === statementId ? { ...se, status: 'matched', matchedTo: newExp.id } : se
    );
    saveState();
    showToast('Captured as expense', D.fmtR(s.amount) + ' — ' + (s.reference || ''));
    closeReconcile();
  }

  function openReconcile() {
    showReconcile = true;
    renderBank();
  }

  function closeReconcile() {
    showReconcile = false;
    renderBank();
  }

  function renderReconcileSheet() {
    const pending = pendingStatements();
    const rows = pending.length === 0 ?
      '<div class="card p-4 text-center text-muted"><i class="bi bi-check-circle" style="font-size:2rem;display:block;margin-bottom:8px"></i>All caught up<div style="font-size:var(--t-xs);margin-top:4px">Every bank entry is matched against a captured income or expense.</div></div>' :
      pending.map(s => {
        const cands = findMatchCandidates(s);
        const acct = accounts.find(a => a.id === s.accountId);
        return '<div class="card p-3 mb-3" style="border-left:4px solid ' + (s.kind === 'in' ? 'var(--c-lime-dark)' : 'var(--c-salmon)') + '">' +
          '<div class="d-flex justify-content-between align-items-start mb-2">' +
            '<div>' +
              '<div class="fw-700 text-teal-dark" style="font-size:var(--t-sm)">' + s.label + '</div>' +
              '<div style="font-size:var(--t-xs);color:var(--ac-warm-gray);font-weight:600">' + D.fmtDate(s.date) + ' · ' + (acct ? acct.bank : '') + ' · ' + s.reference + '</div>' +
            '</div>' +
            '<div class="fw-700 ' + (s.kind === 'in' ? 'text-lime' : 'text-salmon') + '">' + (s.kind === 'in' ? '+ ' : '− ') + D.fmtR(s.amount) + '</div>' +
          '</div>' +
          (cands.length > 0 ?
            '<div class="card p-3 mb-2" style="background:var(--ac-sand);box-shadow:none;border-radius:10px">' +
              '<div style="font-size:var(--t-xxs);font-weight:700;color:var(--ac-warm-gray);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Best matches</div>' +
              cands.map(c => {
                const isExpense = !!c.categoryId;
                const label = isExpense ? (c.vendor || D.EXPENSE_CATEGORIES.find(cat => cat.id === c.categoryId)?.label) : (D.CLIENTS.find(cl => cl.id === c.clientId)?.name || 'Direct sale');
                return '<div class="d-flex justify-content-between align-items-center p-2 mb-1 rounded" style="background:#fff;border:1px solid var(--ac-sand-dark);cursor:pointer" onclick="App.reconcileMatch(\'' + s.id + '\',\'' + c.id + '\')">' +
                  '<div><div class="fw-700 text-teal-dark" style="font-size:var(--t-xs)">' + (label || 'Entry') + '</div>' +
                  '<div style="font-size:0.66rem;color:var(--ac-warm-gray);font-weight:600">' + D.fmtDateShort(c.date) + ' · ' + D.fmtR(c.amount) + '</div></div>' +
                  '<i class="bi bi-link-45deg" style="color:var(--c-teal)"></i>' +
                '</div>';
              }).join('') +
            '</div>' :
            '<div style="font-size:var(--t-xs);color:var(--ac-warm-gray);font-weight:600;margin-bottom:8px">No suggested match</div>'
          ) +
          '<div class="d-flex gap-2">' +
            '<button class="btn btn-sm btn-ghost flex-grow-1" onclick="App.dismissStatement(\'' + s.id + '\')"><i class="bi bi-x"></i> Ignore</button>' +
            (s.kind === 'in'
              ? '<button class="btn btn-sm btn-lime flex-grow-1" onclick="App.captureStatementAsIncome(\'' + s.id + '\')"><i class="bi bi-plus-lg"></i> Capture as income</button>'
              : '<button class="btn btn-sm btn-salmon flex-grow-1" onclick="App.captureStatementAsExpense(\'' + s.id + '\')"><i class="bi bi-plus-lg"></i> Capture as expense</button>'
            ) +
          '</div>' +
        '</div>';
      }).join('');

    return '<div class="sheet-overlay" onclick="App.closeReconcile()">' +
      '<div class="sheet" onclick="event.stopPropagation()">' +
        '<div class="sheet-handle"></div>' +
        '<div class="sheet-head">' +
          '<div>' +
            '<div class="sheet-title">Reconcile bank entries</div>' +
            '<div class="sheet-sub">' + pending.length + ' unmatched · imported from bank statement</div>' +
          '</div>' +
          '<button class="sheet-close" onclick="App.closeReconcile()"><i class="bi bi-x-lg"></i></button>' +
        '</div>' +
        '<div class="sheet-body">' + rows + '</div>' +
        '<div class="sheet-footer">' +
          '<button class="btn btn-teal btn-block" onclick="App.closeReconcile()">Done</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  }

  // ── Initialize state from seed data ────────────────────
  function initState(forceSeed) {
    if (!forceSeed && loadState()) return;
    invoices = JSON.parse(JSON.stringify(D.INVOICES));
    incomeEntries = JSON.parse(JSON.stringify(D.INCOME));
    expenseEntries = JSON.parse(JSON.stringify(D.EXPENSES));
    accounts = JSON.parse(JSON.stringify(D.BANK_ACCOUNTS));
    transactions = JSON.parse(JSON.stringify(D.TRANSACTIONS));
    statementEntries = JSON.parse(JSON.stringify(D.STATEMENT_ENTRIES || [])).map(s => ({ ...s, status: 'pending' }));
  }

  // ── Helpers ────────────────────────────────────────────
  const liTotal = (li) => (li.qty || 0) * (li.unitPrice || 0);
  const invTotal = (inv) => inv.lineItems.reduce((s, li) => s + liTotal(li), 0);
  const invPaid = (inv) => inv.paidLineItemIds.reduce((s, id) => {
    const li = inv.lineItems.find(x => x.id === id);
    return s + (li ? liTotal(li) : 0);
  }, 0);
  const invOutstanding = (inv) => Math.max(0, invTotal(inv) - invPaid(inv));
  const clientById = (id) => D.CLIENTS.find(c => c.id === id);
  const productById = (id) => D.PRODUCTS.find(p => p.id === id);
  const accountById = (id) => accounts.find(a => a.id === id);
  const invoiceById = (id) => invoices.find(i => i.id === id);
  const categoryById = (id) => D.EXPENSE_CATEGORIES.find(c => c.id === id);

  function deriveStatus(inv) {
    const total = invTotal(inv);
    const paid = invPaid(inv);
    if (total <= 0) return inv.status;
    if (paid >= total - 0.01) return 'paid';
    if (paid > 0) return 'partial';
    if (inv.status === 'draft') return 'draft';
    if (inv.status === 'overdue') return 'overdue';
    return 'sent';
  }

  function nextInvoiceId() {
    const nums = invoices.map(i => {
      const m = i.id.match(/INV-2026-(\d+)/);
      return m ? parseInt(m[1], 10) : 0;
    });
    const max = nums.length ? Math.max(...nums) : 0;
    return 'INV-2026-' + String(max + 1).padStart(4, '0');
  }

  let toastCount = 0;

  function showToast(title, message, tone) {
    toastCount++;
    const id = 'toast-' + toastCount;
    const container = document.getElementById('toastContainer');
    const el = document.createElement('div');
    el.className = 'toast-msg';
    el.id = id;
    el.innerHTML = '<i class="bi ' + (tone === 'error' ? 'bi-exclamation-circle-fill' : 'bi-check-circle-fill') + '"></i>' +
      '<div class="toast-body"><div class="toast-title">' + title + '</div>' +
      (message ? '<div style="font-size:var(--t-xs);opacity:0.85;margin-top:2px">' + message + '</div>' : '') +
      '</div>';
    container.appendChild(el);
    setTimeout(() => { const e = document.getElementById(id); if (e) e.remove(); }, 3200);
  }

  // ── Navigation ─────────────────────────────────────────
  function navigate(page, state) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const target = document.getElementById('page-' + page);
    if (target) {
      target.classList.add('active');
      document.querySelector('.app-scroll') && (document.querySelector('.app-scroll').scrollTop = 0);
    }
    currentPage = page;
    if (state && state.invoiceId) currentInvoiceId = state.invoiceId;
    updateTabBar(page);
    renderCurrentView();
  }

  function updateTabBar(page) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    const tabMap = { hub: 'tab-hub', income: 'tab-ledger', invoice: 'tab-invoice', 'invoice-detail': 'tab-invoice', cashflow: 'tab-insights', expense: 'tab-ledger', bank: 'tab-hub' };
    const tabId = tabMap[page] || 'tab-hub';
    const tab = document.getElementById(tabId);
    if (tab) tab.classList.add('active');
  }

  function goBack() {
    const fromInvoiceDetail = currentPage === 'invoice-detail';
    if (currentPage === 'bank' || currentPage === 'income' || currentPage === 'expense' || currentPage === 'invoice' || currentPage === 'cashflow') {
      navigate('hub');
    } else if (currentPage === 'invoice-detail') {
      navigate('invoice');
    } else if (currentPage === 'invoice-new' || currentPage === 'income-new' || currentPage === 'expense-new') {
      navigate(fromInvoiceDetail ? 'invoice-detail' : 'hub');
    } else {
      navigate('hub');
    }
  }

  // ── Rendering ──────────────────────────────────────────
  function renderCurrentView() {
    switch (currentPage) {
      case 'hub': renderHub(); break;
      case 'bank': renderBank(); break;
      case 'income': renderIncome(); break;
      case 'invoice': renderInvoiceList(); break;
      case 'invoice-detail': renderInvoiceDetail(); break;
      case 'cashflow': renderCashflow(); break;
      case 'expense': renderExpenses(); break;
      case 'invoice-new': renderNewInvoiceForm(); break;
      case 'income-new': renderNewIncomeForm(); break;
      case 'expense-new': renderNewExpenseForm(); break;
    }
  }

  // ════════════════════════════════════════════════════════
  // HUB / DASHBOARD
  // ════════════════════════════════════════════════════════
  function renderHub() {
    const totalBank = accounts.reduce((s, a) => s + a.balance, 0);
    const filteredIncomes = filterByDateRange(incomeEntries, dateRange.startDate, dateRange.endDate);
    const filteredExpenses = filterByDateRange(expenseEntries, dateRange.startDate, dateRange.endDate);
    const incomeMonth = filteredIncomes.reduce((s, i) => s + i.amount, 0);
    const expenseMonth = filteredExpenses.reduce((s, e) => s + e.amount, 0);
    const net = incomeMonth - expenseMonth;
    const stats = {
      draft: invoices.filter(i => i.status === 'draft').length,
      sent: invoices.filter(i => i.status === 'sent').length,
      overdue: invoices.filter(i => i.status === 'overdue').length,
      outstanding: invoices.filter(i => ['sent', 'partial', 'overdue'].includes(i.status)).reduce((s, i) => s + invOutstanding(i), 0),
    };

    const overdueInv = invoices.find(i => i.status === 'overdue');
    const recentPay = filteredIncomes.find(i => i.source === 'invoice');
    const directs = filteredIncomes.filter(i => i.source === 'standalone');

    let insightsHtml = '';
    if (overdueInv || recentPay || directs.length >= 2) {
      insightsHtml = '<div class="hub-insights">' +
        '<div class="insights-title"><i class="bi bi-lightbulb"></i> Quick insights</div>';

      if (overdueInv) {
        const c = clientById(overdueInv.clientId);
        insightsHtml += '<div class="insight">' +
          '<div class="insight-icon warn"><i class="bi bi-exclamation-triangle"></i></div>' +
          '<span><strong>' + stats.overdue + ' invoice' + (stats.overdue > 1 ? 's' : '') + ' overdue</strong> — ' + overdueInv.id + ' to ' + (c ? c.name : 'client') + ', ' + D.fmtR(invOutstanding(overdueInv)) + '.</span>' +
          '<button class="insight-action" onclick="App.navigate(\'invoice\')">Open</button></div>';
      }
      if (recentPay) {
        const c = clientById(recentPay.clientId);
        insightsHtml += '<div class="insight">' +
          '<div class="insight-icon pos"><i class="bi bi-cash-coin"></i></div>' +
          '<span><strong>' + D.fmtR(recentPay.amount) + ' came in</strong> from ' + recentPay.invoiceId + ' — payment from ' + (c ? c.name : 'client') + '.</span>' +
          '<button class="insight-action" onclick="App.navigate(\'invoice-detail\',{invoiceId:\'' + recentPay.invoiceId + '\'})">View</button></div>';
      }
      if (directs.length >= 2) {
        insightsHtml += '<div class="insight">' +
          '<div class="insight-icon info"><i class="bi bi-info-circle"></i></div>' +
          '<span><strong>' + directs.length + ' direct sales</strong> aren\'t on any invoice — log them retroactively?</span>' +
          '<button class="insight-action" onclick="App.navigate(\'income\')">Review</button></div>';
      }
      insightsHtml += '</div>';
    }

    const rangeLabel = dateRange.startDate && dateRange.endDate
      ? D.fmtDateShort(dateRange.startDate) + ' – ' + D.fmtDateShort(dateRange.endDate)
      : 'All time';

    document.getElementById('hubContent').innerHTML =
      '<div class="hub-greeting">' +
        '<div class="hub-greet-name">' + D.BUSINESS.name + '</div>' +
        '<div class="hub-greet-date">Friday, 15 May</div>' +
      '</div>' +
      renderDateRangePicker() +
      '<div class="hub-hero">' +
        '<div class="hub-hero-left">' +
          '<div class="hub-hero-label">Net cashflow · ' + rangeLabel + '</div>' +
          '<div class="hub-hero-amount ' + (net >= 0 ? 'pos' : 'neg') + '">' + (net >= 0 ? '+' : '− ') + D.fmtR(Math.abs(net)) + '</div>' +
          '<div class="hub-hero-detail">' +
            '<span><span class="dot dot-green"></span> ' + D.fmtRShort(incomeMonth) + ' in</span>' +
            '<span><span class="dot dot-red"></span> ' + D.fmtRShort(expenseMonth) + ' out</span>' +
          '</div>' +
        '</div>' +
        '<button class="hub-hero-cta" onclick="App.navigate(\'cashflow\')"><i class="bi bi-graph-up-arrow"></i><span>See trend</span></button>' +
      '</div>' +
      '<div class="hub-grid">' +
        /* Bank Card */
        '<div class="hub-card teal">' +
          '<div class="hub-card-head">' +
            '<div class="hub-card-icon teal"><i class="bi bi-bank2"></i></div>' +
            '<div class="flex-grow-1"><div class="hub-card-title">Bank</div><div class="hub-card-metric-label">Total balance</div></div>' +
          '</div>' +
          '<div class="hub-card-value">' + D.fmtR(totalBank) + '</div>' +
          '<div class="hub-card-sub">' + accounts.length + ' accounts · 1 primary</div>' +
          '<div class="hub-card-options">' +
            '<button class="hub-opt primary" onclick="App.navigate(\'bank\')"><i class="bi bi-list-ul"></i><span>View accounts</span></button>' +
            '<button class="hub-opt" onclick="App.navigate(\'bank\')"><i class="bi bi-plus-lg"></i><span>Add account</span></button>' +
          '</div>' +
        '</div>' +
        /* Income Card */
        '<div class="hub-card lime">' +
          '<div class="hub-card-head">' +
            '<div class="hub-card-icon lime"><i class="bi bi-arrow-down-left-circle"></i></div>' +
            '<div><div class="hub-card-title">Income</div><div class="hub-card-metric-label">' + rangeLabel + '</div></div>' +
          '</div>' +
          '<div class="hub-card-value">' + D.fmtR(incomeMonth) + '</div>' +
          '<div class="hub-card-sub">' + filteredIncomes.length + ' entries</div>' +
          '<div class="hub-card-options">' +
            '<button class="hub-opt primary" onclick="App.navigate(\'income-new\')"><i class="bi bi-plus-circle"></i><span>Log income</span></button>' +
            '<button class="hub-opt" onclick="App.navigate(\'income\')"><i class="bi bi-list-check"></i><span>View ledger</span></button>' +
          '</div>' +
        '</div>' +
        /* Invoice Card */
        '<div class="hub-card" style="border-color:rgba(61,138,151,0.3)">' +
          '<div class="hub-card-head">' +
            '<div class="hub-card-icon teal"><i class="bi bi-receipt-cutoff"></i></div>' +
            '<div><div class="hub-card-title">Invoice</div><div class="hub-card-metric-label">Outstanding</div></div>' +
          '</div>' +
          '<div class="hub-card-value">' + D.fmtR(stats.outstanding) + '</div>' +
          '<div class="hub-card-sub">' +
            '<span class="badge bg-salmon me-1">' + stats.overdue + ' overdue</span>' +
            '<span class="badge bg-teal me-1">' + stats.sent + ' sent</span>' +
            '<span class="badge bg-secondary">' + stats.draft + ' draft</span>' +
          '</div>' +
          '<div class="hub-card-options">' +
            '<button class="hub-opt primary" onclick="App.navigate(\'invoice-new\')"><i class="bi bi-plus-lg"></i><span>New invoice</span></button>' +
            '<button class="hub-opt" onclick="App.navigate(\'invoice\')"><i class="bi bi-list-ul"></i><span>All invoices</span></button>' +
          '</div>' +
        '</div>' +
        /* Cashflow Card */
        '<div class="hub-card lime">' +
          '<div class="hub-card-head">' +
            '<div class="hub-card-icon lime"><i class="bi bi-graph-up-arrow"></i></div>' +
            '<div><div class="hub-card-title">Cashflow</div><div class="hub-card-metric-label">Last 5 weeks</div></div>' +
          '</div>' +
          '<div class="hub-card-value" style="font-size:var(--t-sm)"><span class="fw-700">Forecast: ' + D.fmtR(stats.outstanding) + '</span> in pipeline</div>' +
          '<div class="hub-card-sub">&nbsp;</div>' +
          '<div class="hub-card-options">' +
            '<button class="hub-opt primary" onclick="App.navigate(\'cashflow\')"><i class="bi bi-bar-chart"></i><span>Money in vs out</span></button>' +
          '</div>' +
        '</div>' +
        /* Expenses Card */
        '<div class="hub-card salmon">' +
          '<div class="hub-card-head">' +
            '<div class="hub-card-icon salmon"><i class="bi bi-arrow-up-right-circle"></i></div>' +
            '<div><div class="hub-card-title">Expenses</div><div class="hub-card-metric-label">' + rangeLabel + '</div></div>' +
          '</div>' +
          '<div class="hub-card-value">' + D.fmtR(expenseMonth) + '</div>' +
          '<div class="hub-card-sub">' + filteredExpenses.length + ' entries</div>' +
          '<div class="hub-card-options">' +
            '<button class="hub-opt primary" onclick="App.navigate(\'expense-new\')"><i class="bi bi-plus-circle"></i><span>Log expense</span></button>' +
            '<button class="hub-opt" onclick="App.navigate(\'expense\')"><i class="bi bi-list-check"></i><span>View ledger</span></button>' +
          '</div>' +
        '</div>' +
      '</div>' +
      insightsHtml +
      '<div class="hub-footer">Avovision · AvoConnect<br><span style="opacity:0.7">My Finances · interactive demo</span></div>' +
      '<div class="text-center mt-3" style="padding-bottom:24px">' +
        '<button class="btn btn-sm btn-ghost text-muted" onclick="App.resetToSeed()" style="font-size:var(--t-xs);opacity:0.6"><i class="bi bi-arrow-counterclockwise"></i> Reset to seed data</button>' +
      '</div>';
  }

  // ════════════════════════════════════════════════════════
  // BANK VIEW
  // ════════════════════════════════════════════════════════
  function renderBank() {
    const totalBank = accounts.reduce((s, a) => s + a.balance, 0);
    let activeAccountId = 'ba_001';

    const filteredTx = filterByDateRange(transactions, dateRange.startDate, dateRange.endDate);
    const rangeLabel = dateRange.startDate && dateRange.endDate
      ? D.fmtDateShort(dateRange.startDate) + ' – ' + D.fmtDateShort(dateRange.endDate)
      : 'All time';

    const accCards = accounts.map(a =>
      '<div class="bank-acc-card" style="--acc-color:' + a.color + '" onclick="App.selectBankAccount(\'' + a.id + '\')" id="bank-acc-' + a.id + '">' +
        '<div class="d-flex justify-content-between align-items-center mb-1">' +
          '<div class="bank-acc-bank">' + a.bank + '</div>' +
          (a.isPrimary ? '<span class="badge bg-lime" style="font-size:0.6rem">Primary</span>' : '') +
        '</div>' +
        '<div class="bank-acc-name">' + a.name + '</div>' +
        '<div class="bank-acc-num">' + a.accountNumber + '</div>' +
        '<div class="bank-acc-bal">' + D.fmtR(a.balance) + '</div>' +
      '</div>'
    ).join('');

    const txHtml = filteredTx.slice(0, 10).map(t => {
      const isIn = t.kind === 'in';
      return '<div class="ledger-row">' +
        '<div class="ledger-icon ' + (isIn ? 'txn-in' : 'txn-out') + '"><i class="bi ' + (isIn ? 'bi-arrow-down-left' : 'bi-arrow-up-right') + '"></i></div>' +
        '<div class="ledger-body"><div class="ledger-label">' + t.label + '</div><div class="ledger-meta">' + D.fmtDateShort(t.date) + '</div></div>' +
        '<div class="ledger-amount ' + (isIn ? 'pos' : 'neg') + '">' + (isIn ? '+' : '− ') + D.fmtR(t.amount) + '</div>' +
      '</div>';
    }).join('');

    const pending = pendingStatements();
    const pendingCount = pending.length;
    const reconAlert = pendingCount > 0 ?
      '<div class="recon-alert" onclick="App.openReconcile()">' +
        '<div class="recon-alert-icon"><i class="bi bi-arrow-down-up"></i></div>' +
        '<div class="recon-alert-body">' +
          '<div class="recon-alert-title">' + pendingCount + ' bank entr' + (pendingCount > 1 ? 'ies' : 'y') + ' to reconcile</div>' +
          '<div class="recon-alert-sub">Match imported statement to your captured income and expenses</div>' +
        '</div>' +
        '<i class="bi bi-chevron-right recon-alert-chev"></i>' +
      '</div>' : '';

    document.getElementById('bankContent').innerHTML =
      '<div class="bank-total">' +
        '<div class="bank-total-label">Total balance across all accounts</div>' +
        '<div class="bank-total-amount">' + D.fmtR(totalBank) + '</div>' +
      '</div>' +
      reconAlert +
      renderDateRangePicker() +
      '<div class="section-label">Accounts</div>' +
      '<div class="bank-accounts-scroll" id="bankAccScroll">' + accCards + '</div>' +
      '<div class="bank-action-grid">' +
        '<button class="bank-action" onclick="App.openReconcile()"><i class="bi bi-arrow-down-up"></i><span>Reconcile</span>' +
          (pendingCount > 0 ? '<span class="bank-action-badge">' + pendingCount + '</span>' : '') +
        '</button>' +
        '<button class="bank-action"><i class="bi bi-arrow-left-right"></i><span>Transfer</span></button>' +
        '<button class="bank-action"><i class="bi bi-file-earmark-arrow-down"></i><span>Statement</span></button>' +
        '<button class="bank-action"><i class="bi bi-gear"></i><span>Settings</span></button>' +
      '</div>' +
      '<div class="section-label">Recent activity · ' + rangeLabel + '</div>' +
      '<div class="card p-3">' + txHtml + '</div>' +
      (showReconcile ? renderReconcileSheet() : '');

    // Set active first account
    document.getElementById('bank-acc-' + activeAccountId)?.classList.add('active');
  }

  // Expose App methods globally
  window.App = window.App || {};
  App.selectBankAccount = function (id) {
    document.querySelectorAll('.bank-acc-card').forEach(c => c.classList.remove('active'));
    const el = document.getElementById('bank-acc-' + id);
    if (el) el.classList.add('active');
  };

  // ════════════════════════════════════════════════════════
  // INCOME VIEW
  // ════════════════════════════════════════════════════════
  let incomeFilter = 'all';

  function renderIncome() {
    const dateFiltered = filterByDateRange(incomeEntries, dateRange.startDate, dateRange.endDate);
    const filtered = dateFiltered.filter(i => {
      if (incomeFilter === 'all') return true;
      if (incomeFilter === 'invoice') return i.source === 'invoice';
      if (incomeFilter === 'direct') return i.source === 'standalone';
      return true;
    });
    const total = filtered.reduce((s, i) => s + i.amount, 0);

    const rangeLabel = dateRange.startDate && dateRange.endDate
      ? D.fmtDateShort(dateRange.startDate) + ' – ' + D.fmtDateShort(dateRange.endDate)
      : 'All time';

    const rows = filtered.map(inc => {
      const client = clientById(inc.clientId);
      const product = inc.productId ? productById(inc.productId) : null;
      const acct = accountById(inc.bankAccountId);
      const isInvoice = inc.source === 'invoice';
      return '<div class="ledger-row">' +
        '<div class="ledger-icon ' + (isInvoice ? 'invoice' : 'direct') + '"><i class="bi ' + (isInvoice ? 'bi-receipt' : 'bi-cash-coin') + '"></i></div>' +
        '<div class="ledger-body">' +
          '<div class="ledger-label">' + (client ? client.name : 'Walk-in sale') + (product ? '<span class="text-muted fw-600"> · ' + product.label + '</span>' : '') + '</div>' +
          '<div class="ledger-meta">' +
            (isInvoice ? '<span class="text-teal fw-700">' + inc.invoiceId + '</span>' : '<span>' + inc.method + '</span>') +
            '<span>·</span><span>' + D.fmtDateShort(inc.date) + '</span>' +
            (acct ? '<span>·</span><span>' + acct.bank + '</span>' : '') +
          '</div>' +
        '</div>' +
        '<div class="ledger-amount pos">+ ' + D.fmtR(inc.amount) + '</div>' +
      '</div>';
    }).join('');

    document.getElementById('incomeContent').innerHTML =
      renderDateRangePicker() +
      '<div class="card p-3 mb-3" style="border-left:4px solid var(--c-lime)">' +
        '<div class="section-label" style="margin:0 0 4px">' +
          (incomeFilter === 'all' ? 'All income · ' + rangeLabel : incomeFilter === 'invoice' ? 'From invoices · ' + rangeLabel : 'Direct sales · ' + rangeLabel) +
        '</div>' +
        '<div class="fs-2 fw-700" style="color:var(--c-lime-dark)">' + D.fmtR(total) + '</div>' +
        '<div class="text-muted fw-600" style="font-size:var(--t-xs)">' + filtered.length + ' entries</div>' +
      '</div>' +
      '<div class="filter-tabs">' +
        '<button class="filter-tab ' + (incomeFilter === 'all' ? 'active' : '') + '" onclick="App.setIncomeFilter(\'all\')">All</button>' +
        '<button class="filter-tab ' + (incomeFilter === 'invoice' ? 'active' : '') + '" onclick="App.setIncomeFilter(\'invoice\')">From invoice</button>' +
        '<button class="filter-tab ' + (incomeFilter === 'direct' ? 'active' : '') + '" onclick="App.setIncomeFilter(\'direct\')">Direct sales</button>' +
      '</div>' +
      '<button class="btn btn-lime btn-block mb-3" onclick="App.navigate(\'income-new\')"><i class="bi bi-plus-circle"></i> Log new income</button>' +
      '<div class="section-label">Ledger</div>' +
      '<div class="card p-3">' + (rows || '<div class="text-center py-4 text-muted">No entries</div>') + '</div>';
  }

  App.setIncomeFilter = function (f) { incomeFilter = f; renderIncome(); };

  // ════════════════════════════════════════════════════════
  // INVOICE LIST
  // ════════════════════════════════════════════════════════
  let invoiceFilter = 'all';

  function renderInvoiceList() {
    const dateFiltered = filterByIssueDate(invoices, dateRange.startDate, dateRange.endDate);
    const filtered = invoiceFilter === 'all' ? dateFiltered : dateFiltered.filter(i => i.status === invoiceFilter);
    const stats = {
      all: dateFiltered.length,
      draft: dateFiltered.filter(i => i.status === 'draft').length,
      sent: dateFiltered.filter(i => i.status === 'sent').length,
      partial: dateFiltered.filter(i => i.status === 'partial').length,
      overdue: dateFiltered.filter(i => i.status === 'overdue').length,
      paid: dateFiltered.filter(i => i.status === 'paid').length,
      outstanding: dateFiltered.filter(i => ['sent','partial','overdue'].includes(i.status)).reduce((s, i) => s + invOutstanding(i), 0),
    };

    const rangeLabel = dateRange.startDate && dateRange.endDate
      ? D.fmtDateShort(dateRange.startDate) + ' – ' + D.fmtDateShort(dateRange.endDate)
      : 'All time';

    const cards = filtered.map(inv => {
      const client = clientById(inv.clientId);
      const total = invTotal(inv);
      const outstanding = invOutstanding(inv);
      return '<div class="invoice-card" onclick="App.navigate(\'invoice-detail\',{invoiceId:\'' + inv.id + '\'})">' +
        '<div class="invoice-card-head"><div class="invoice-id">' + inv.id + '</div><span class="pill pill-' + inv.status + '">' + inv.status + '</span></div>' +
        '<div class="invoice-client">' + (client ? client.name : '—') + '</div>' +
        '<div class="invoice-meta"><i class="bi bi-calendar3"></i> ' + D.fmtDateShort(inv.issueDate) +
          (inv.dueDate ? ' · Due ' + D.fmtDateShort(inv.dueDate) : '') + '</div>' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-end">' +
          '<div class="invoice-amount-main">' + D.fmtR(total) + '</div>' +
          (outstanding > 0 && outstanding < total ? '<div class="invoice-amount-out">' + D.fmtR(outstanding) + ' outstanding</div>' : '') +
          (inv.status === 'paid' ? '<div style="color:var(--c-lime-dark);font-size:var(--t-xs);font-weight:700"><i class="bi bi-check-circle-fill"></i> Paid</div>' : '') +
        '</div>' +
      '</div>';
    }).join('');

    document.getElementById('invoiceContent').innerHTML =
      renderDateRangePicker() +
      '<div class="card p-3 mb-3 d-flex justify-content-between align-items-center" style="background:linear-gradient(135deg,#fff,var(--ac-sand))">' +
        '<div><div class="section-label" style="margin:0 0 4px">Outstanding · ' + rangeLabel + '</div><div class="fs-2 fw-700 text-teal-dark">' + D.fmtR(stats.outstanding) + '</div></div>' +
        '<div style="font-size:var(--t-xs);color:var(--ac-warm-gray)">' +
          '<div><span class="dot" style="background:var(--c-salmon);width:8px;height:8px;display:inline-block;border-radius:50%;margin-right:4px;vertical-align:middle"></span>' + stats.overdue + ' overdue</div>' +
          '<div><span class="dot" style="background:var(--c-teal);width:8px;height:8px;display:inline-block;border-radius:50%;margin-right:4px;vertical-align:middle"></span>' + stats.sent + ' sent</div>' +
          '<div><span class="dot" style="background:#f4a261;width:8px;height:8px;display:inline-block;border-radius:50%;margin-right:4px;vertical-align:middle"></span>' + stats.partial + ' part-paid</div>' +
        '</div>' +
      '</div>' +
      '<div class="filter-tabs">' +
        ['all','overdue','sent','partial','draft','paid'].map(f =>
          '<button class="filter-tab ' + (invoiceFilter === f ? 'active' : '') + '" onclick="App.setInvoiceFilter(\'' + f + '\')">' +
            f.charAt(0).toUpperCase() + f.slice(1) + ' ' + stats[f] +
          '</button>'
        ).join('') +
      '</div>' +
      '<button class="btn btn-teal btn-block mb-3" onclick="App.navigate(\'invoice-new\')"><i class="bi bi-plus-lg"></i> Create new invoice</button>' +
      '<div class="section-label">' + filtered.length + ' invoice' + (filtered.length !== 1 ? 's' : '') + '</div>' +
      '<div>' + (cards || '<div class="card p-4 text-center text-muted">No invoices here</div>') + '</div>';
  }

  App.setInvoiceFilter = function (f) { invoiceFilter = f; renderInvoiceList(); };

  // ════════════════════════════════════════════════════════
  // INVOICE DETAIL
  // ════════════════════════════════════════════════════════
  function renderInvoiceDetail() {
    const inv = invoiceById(currentInvoiceId);
    if (!inv) {
      document.getElementById('invoiceDetailContent').innerHTML =
        '<div class="card p-4 text-center text-muted"><div class="fs-1 mb-3"><i class="bi bi-question-circle"></i></div><div class="fw-700">Invoice not found</div></div>';
      return;
    }
    const client = clientById(inv.clientId);
    const total = invTotal(inv);
    const paid = invPaid(inv);
    const outstanding = invOutstanding(inv);

    const liHtml = inv.lineItems.map(li => {
      const p = productById(li.productId);
      const isPaid = inv.paidLineItemIds.includes(li.id);
      return '<div class="li-row' + (isPaid ? ' paid' : '') + '">' +
        '<div style="text-align:center">' +
          (isPaid
            ? '<i class="bi bi-check-circle-fill" style="color:var(--c-lime-dark);font-size:1.2rem"></i>'
            : '<i class="bi bi-square" style="color:var(--ac-warm-gray);font-size:1.2rem"></i>') +
        '</div>' +
        '<div><div class="li-product">' + (p ? p.label : li.description || 'Item') + '</div>' +
          '<div class="li-meta">' + li.qty + ' ' + (li.unit || (p ? p.unit : '')) + ' × ' + D.fmtR(li.unitPrice) + '</div></div>' +
        '<div class="li-amount fw-700">' + D.fmtR(liTotal(li)) + '</div>' +
      '</div>';
    }).join('') +
    '<div class="li-row" style="border-top:2px solid rgba(47,111,122,0.15);padding-top:10px;margin-top:4px">' +
      '<div></div><div><div class="li-product">Total</div></div>' +
      '<div class="li-amount fw-700" style="font-size:var(--t-lg);color:var(--c-teal-dark)">' + D.fmtR(total) + '</div>' +
    '</div>';

    const linkedIncome = incomeEntries.filter(i => i.invoiceId === inv.id);
    const linkedHtml = linkedIncome.map(inc =>
      '<div class="ledger-row">' +
        '<div class="ledger-icon direct"><i class="bi bi-cash-coin"></i></div>' +
        '<div class="ledger-body"><div class="ledger-label">' + D.fmtR(inc.amount) + ' via ' + inc.method.toUpperCase() + '</div>' +
          '<div class="ledger-meta">' + D.fmtDate(inc.date) + ' · ' + (accountById(inc.bankAccountId)?.bank || '') + '</div></div>' +
        '<div class="ledger-amount pos">+ ' + D.fmtR(inc.amount) + '</div>' +
      '</div>'
    ).join('');

    document.getElementById('invoiceDetailContent').innerHTML =
      '<div class="invoice-hero' + (inv.status === 'paid' ? ' paid' : inv.status === 'overdue' ? ' overdue' : inv.status === 'draft' ? ' draft' : '') + '">' +
        '<div class="d-flex justify-content-between align-items-center mb-2">' +
          '<span class="pill pill-' + inv.status + '" style="background:rgba(255,255,255,0.16);color:#fff">' + inv.status + '</span>' +
          (inv.dueDate ? '<span style="font-size:var(--t-xs);font-weight:700;opacity:0.8">Due ' + D.fmtDateShort(inv.dueDate) + '</span>' : '') +
        '</div>' +
        '<div class="invoice-hero-amount">' + D.fmtR(total) + '</div>' +
        (paid > 0 ? '<div style="margin-top:6px;font-size:var(--t-xs);opacity:0.85">' + D.fmtR(paid) + ' paid · ' + D.fmtR(outstanding) + ' outstanding</div>' : '<div style="margin-top:6px;font-size:var(--t-xs);opacity:0.85">No payments yet</div>') +
      '</div>' +

      '<div class="d-flex gap-2 mb-3">' +
        (outstanding > 0 && inv.status !== 'draft'
          ? '<button class="btn btn-lime flex-grow-1" data-bs-toggle="modal" data-bs-target="#paymentModal"><i class="bi bi-cash-coin"></i> Record payment</button>'
          : '') +
        (inv.status === 'draft'
          ? '<button class="btn btn-teal flex-grow-1" onclick="App.sendInvoice(\'' + inv.id + '\')"><i class="bi bi-send"></i> Send invoice</button>'
          : '') +
        '<a class="btn btn-ghost flex-grow-1" href="/invoices/' + inv.id + '/pdf" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;gap:6px;text-decoration:none"><i class="bi bi-filetype-pdf"></i> PDF</a>' +
      '</div>' +

      '<div class="section-label">Details</div>' +
      '<div class="card p-3 mb-3" style="background:var(--ac-sand)">' +
        '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Client</span><span class="fw-700 text-teal-dark">' + (client ? client.name : '—') + '</span></div>' +
        '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Contact</span><span class="fw-700 text-teal-dark">' + (client ? client.contact : '—') + '</span></div>' +
        '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Issued</span><span class="fw-700 text-teal-dark">' + D.fmtDate(inv.issueDate) + '</span></div>' +
        '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Due</span><span class="fw-700 text-teal-dark">' + D.fmtDate(inv.dueDate) + '</span></div>' +
        '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Terms</span><span class="fw-700 text-teal-dark">' + inv.paymentTerms + '</span></div>' +
        (inv.notes ? '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Notes</span><span class="fw-700 text-teal-dark">' + inv.notes + '</span></div>' : '') +
      '</div>' +

      '<div class="section-label">Line items</div>' +
      '<div class="card p-3 mb-3">' + liHtml + '</div>' +

      (linkedHtml ? '<div class="section-label">Payments received</div><div class="card p-3">' + linkedHtml + '</div>' : '') +

      (outstanding > 0 ? renderPaymentForm(inv) : '');
  }

  function renderPaymentForm(inv) {
    const outstanding = invOutstanding(inv);
    return '<div class="card p-3 mt-3" id="paymentForm">' +
      '<h6 class="fw-700 text-teal-dark mb-3">Record a payment</h6>' +
      '<div class="mb-3">' +
        '<label class="form-label">Amount (R)</label>' +
        '<input type="number" class="form-control" id="payAmount" value="' + outstanding.toFixed(2) + '" step="0.01">' +
      '</div>' +
      '<div class="row g-2 mb-3">' +
        '<div class="col-6"><label class="form-label">Date</label><input type="date" class="form-control" id="payDate" value="2026-05-15"></div>' +
        '<div class="col-6"><label class="form-label">Method</label><select class="form-select" id="payMethod"><option value="eft">EFT</option><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile</option></select></div>' +
      '</div>' +
      '<div class="mb-3"><label class="form-label">Note</label><input type="text" class="form-control" id="payNote" placeholder="Reference..."></div>' +
      '<button class="btn btn-lime btn-block" onclick="App.recordPayment(\'' + inv.id + '\')"><i class="bi bi-check-lg"></i> Record ' + D.fmtR(outstanding) + '</button>' +
    '</div>';
  }

  App.sendInvoice = function (id) {
    const inv = invoices.find(i => i.id === id);
    if (inv) { inv.status = 'sent'; saveState(); showToast('Invoice sent', id + ' has been sent to the client'); renderInvoiceDetail(); }
  };

  App.recordPayment = function (invoiceId) {
    const inv = invoices.find(i => i.id === invoiceId);
    if (!inv) return;
    const amount = parseFloat(document.getElementById('payAmount').value);
    const date = document.getElementById('payDate').value;
    const method = document.getElementById('payMethod').value;
    const note = document.getElementById('payNote').value;
    if (!amount || amount <= 0) { showToast('Error', 'Enter a valid amount', 'error'); return; }

    // Mark all line items as paid
    const allLiIds = inv.lineItems.map(li => li.id);
    inv.paidLineItemIds = allLiIds;
    inv.status = deriveStatus(inv);

    const newInc = {
      id: 'inc_' + Date.now(),
      date, source: 'invoice', invoiceId,
      clientId: inv.clientId,
      amount, bankAccountId: inv.bankAccountId,
      method, note: note || 'Payment against ' + invoiceId,
    };
    incomeEntries.unshift(newInc);

    const acct = accounts.find(a => a.id === inv.bankAccountId);
    if (acct) acct.balance += amount;

    transactions.unshift({
      id: 't_' + Date.now(), date, kind: 'in', amount,
      accountId: inv.bankAccountId,
      label: invoiceId + ' — ' + (clientById(inv.clientId)?.name || 'Payment'),
      ref: newInc.id,
    });

    saveState();
    showToast('Payment recorded', D.fmtR(amount) + ' from ' + (clientById(inv.clientId)?.name || 'client'));
    renderInvoiceDetail();
  };

  // ════════════════════════════════════════════════════════
  // CASHFLOW VIEW
  // ════════════════════════════════════════════════════════
  let cfTab = 'trend';

  function renderCashflow() {
    const filteredIncomes = filterByDateRange(incomeEntries, dateRange.startDate, dateRange.endDate);
    const filteredExpenses = filterByDateRange(expenseEntries, dateRange.startDate, dateRange.endDate);
    const incomeMonth = filteredIncomes.reduce((s, i) => s + i.amount, 0);
    const expenseMonth = filteredExpenses.reduce((s, e) => s + e.amount, 0);
    const net = incomeMonth - expenseMonth;
    const stats = { outstanding: invoices.filter(i => ['sent','partial','overdue'].includes(i.status)).reduce((s, i) => s + invOutstanding(i), 0) };
    const rangeLabel = dateRange.startDate && dateRange.endDate
      ? D.fmtDateShort(dateRange.startDate) + ' – ' + D.fmtDateShort(dateRange.endDate)
      : 'All time';

    // Bar chart
    const max = Math.max(...D.WEEKLY_CASHFLOW.flatMap(d => [d.moneyIn, d.moneyOut]));
    const barsHtml = D.WEEKLY_CASHFLOW.map(d =>
      '<div style="display:flex;flex-direction:column;align-items:center;height:100%">' +
        '<div class="cf-bar">' +
          '<div class="cf-bar-inner in" style="height:' + ((d.moneyIn / max) * 100) + '%"></div>' +
          '<div class="cf-bar-inner out" style="height:' + ((d.moneyOut / max) * 100) + '%"></div>' +
        '</div>' +
        '<div style="margin-top:6px;font-size:var(--t-xxs);font-weight:700;color:var(--ac-warm-gray)">' + d.week + '</div>' +
      '</div>'
    ).join('');

    const forecastInv = invoices.filter(inv => ['sent','partial','overdue'].includes(inv.status));
    const forecastHtml = forecastInv.map(inv => {
      const client = clientById(inv.clientId);
      const out = invOutstanding(inv);
      return '<div class="d-flex justify-content-between align-items-start py-2" style="border-bottom:1px solid rgba(232,223,210,0.6);cursor:pointer" onclick="App.navigate(\'invoice-detail\',{invoiceId:\'' + inv.id + '\'})">' +
        '<div><div class="fw-700 text-teal-dark" style="font-size:var(--t-sm)">' + (client ? client.name : '') + '</div>' +
          '<div style="font-size:var(--t-xxs);color:var(--ac-warm-gray);font-weight:600">' + inv.id + ' · Due ' + D.fmtDateShort(inv.dueDate) + '</div></div>' +
        '<div class="text-end"><span class="pill pill-' + inv.status + '">' + inv.status + '</span><div class="fw-700 text-teal-dark" style="font-size:var(--t-sm)">' + D.fmtR(out) + '</div></div>' +
      '</div>';
    }).join('');

    // Product breakdown (use date-filtered income + date-filtered paid invoices)
    const byProduct = {};
    filteredIncomes.forEach(i => { if (i.productId) byProduct[i.productId] = (byProduct[i.productId] || 0) + i.amount; });
    const paidFilteredInvoices = filterByIssueDate(
      invoices.filter(inv => inv.status === 'paid' || inv.status === 'partial'),
      dateRange.startDate, dateRange.endDate
    );
    paidFilteredInvoices.forEach(inv => {
      inv.lineItems.forEach(li => {
        if (li.productId) byProduct[li.productId] = (byProduct[li.productId] || 0) + liTotal(li);
      });
    });
    const prodRows = Object.entries(byProduct)
      .map(([pid, amt]) => ({ product: productById(pid), amount: amt }))
      .filter(r => r.product)
      .sort((a, b) => b.amount - a.amount);
    const prodMax = prodRows.length ? Math.max(...prodRows.map(r => r.amount)) : 0;
    const prodHtml = prodRows.map(r =>
      '<div class="pb-row">' +
        '<div class="fw-700 text-teal-dark" style="font-size:var(--t-xs)">' + r.product.label + '</div>' +
        '<div class="pb-bar-track"><div class="pb-bar-fill" style="width:' + ((r.amount / prodMax) * 100) + '%"></div></div>' +
        '<div class="fw-700 text-teal-dark text-end" style="font-size:var(--t-xs)">' + D.fmtRShort(r.amount) + '</div>' +
      '</div>'
    ).join('');

    document.getElementById('cashflowContent').innerHTML =
      renderDateRangePicker() +
      '<div class="cf-summary">' +
        '<div class="row g-2">' +
          '<div class="col-4"><div class="section-label" style="margin:0">In · ' + rangeLabel + '</div><div class="fs-5 fw-700" style="color:var(--c-lime-dark)">' + D.fmtR(incomeMonth) + '</div></div>' +
          '<div class="col-4"><div class="section-label" style="margin:0">Out · ' + rangeLabel + '</div><div class="fs-5 fw-700 text-salmon">' + D.fmtR(expenseMonth) + '</div></div>' +
          '<div class="col-4 border-start"><div class="section-label" style="margin:0">Net</div>' +
            '<div class="fs-5 fw-700 ' + (net >= 0 ? 'text-lime' : 'text-salmon') + '">' + (net >= 0 ? '+' : '− ') + D.fmtR(Math.abs(net)) + '</div></div>' +
        '</div>' +
      '</div>' +
      '<div class="filter-tabs">' +
        '<button class="filter-tab ' + (cfTab === 'trend' ? 'active' : '') + '" onclick="App.setCfTab(\'trend\')">Trend</button>' +
        '<button class="filter-tab ' + (cfTab === 'forecast' ? 'active' : '') + '" onclick="App.setCfTab(\'forecast\')">Forecast</button>' +
        '<button class="filter-tab ' + (cfTab === 'product' ? 'active' : '') + '" onclick="App.setCfTab(\'product\')">By product</button>' +
      '</div>' +
      (cfTab === 'trend' ? '<div class="card p-3"><div class="section-label">5-week money in vs out</div><div class="cf-bars">' + barsHtml + '</div>' +
        '<div class="text-center mt-3" style="font-size:var(--t-xs);font-weight:700;color:var(--ac-warm-gray)">' +
          '<span class="me-3"><span class="dot" style="background:var(--c-lime);width:10px;height:10px;display:inline-block;border-radius:50%;margin-right:4px;vertical-align:middle"></span> Money in</span>' +
          '<span><span class="dot" style="background:var(--c-salmon);width:10px;height:10px;display:inline-block;border-radius:50%;margin-right:4px;vertical-align:middle"></span> Money out</span>' +
        '</div></div>' : '') +
      (cfTab === 'forecast' ? '<div class="card p-3"><div class="d-flex justify-content-between align-items-start mb-2">' +
        '<div><div class="section-label" style="margin:0">Projected income</div><div style="font-size:var(--t-xs);color:var(--ac-warm-gray);font-weight:600">From open invoices in next 30 days</div></div>' +
        '<div class="fs-4 fw-700 text-teal-dark">' + D.fmtR(stats.outstanding) + '</div></div>' +
        '<hr>' + (forecastHtml || '<div class="text-center py-3 text-muted">No open invoices</div>') + '</div>' : '') +
      (cfTab === 'product' ? '<div class="card p-3"><div class="section-label">Revenue by product · ' + rangeLabel + '</div>' +
        (prodHtml || '<div class="text-center py-3 text-muted">No revenue yet</div>') + '</div>' : '');
  }

  App.setCfTab = function (t) { cfTab = t; renderCashflow(); };

  // ════════════════════════════════════════════════════════
  // EXPENSES VIEW
  // ════════════════════════════════════════════════════════
  let expenseGroup = 'date';

  function renderExpenses() {
    const dateFiltered = filterByDateRange(expenseEntries, dateRange.startDate, dateRange.endDate);
    const total = dateFiltered.reduce((s, e) => s + e.amount, 0);
    const rangeLabel = dateRange.startDate && dateRange.endDate
      ? D.fmtDateShort(dateRange.startDate) + ' – ' + D.fmtDateShort(dateRange.endDate)
      : 'All time';

    if (expenseGroup === 'date') {
      const rows = dateFiltered.map(exp => {
        const cat = categoryById(exp.categoryId);
        const acct = accountById(exp.bankAccountId);
        return '<div class="ledger-row">' +
          '<div class="ledger-icon expense"><i class="bi ' + (cat ? cat.icon : 'bi-tag') + '"></i></div>' +
          '<div class="ledger-body">' +
            '<div class="ledger-label">' + (exp.vendor || (cat ? cat.label : 'Expense')) + '</div>' +
            '<div class="ledger-meta"><span>' + (cat ? cat.label : '') + '</span><span>·</span><span>' + D.fmtDateShort(exp.date) + '</span>' +
              (acct ? '<span>·</span><span>' + acct.bank + '</span>' : '') + '</div>' +
          '</div>' +
          '<div class="ledger-amount neg">− ' + D.fmtR(exp.amount) + '</div>' +
        '</div>';
      }).join('');

      document.getElementById('expenseContent').innerHTML =
        renderDateRangePicker() +
        '<div class="card p-3 mb-3" style="border-left:4px solid var(--c-salmon)">' +
          '<div class="section-label" style="margin:0 0 4px">Expenses · ' + rangeLabel + '</div>' +
          '<div class="fs-2 fw-700 text-salmon">' + D.fmtR(total) + '</div>' +
          '<div class="text-muted fw-600" style="font-size:var(--t-xs)">' + dateFiltered.length + ' entries · ' + new Set(dateFiltered.map(e=>e.categoryId)).size + ' categories</div>' +
        '</div>' +
        '<div class="filter-tabs">' +
          '<button class="filter-tab ' + (expenseGroup === 'date' ? 'active' : '') + '" onclick="App.setExpenseGroup(\'date\')">By date</button>' +
          '<button class="filter-tab ' + (expenseGroup === 'category' ? 'active' : '') + '" onclick="App.setExpenseGroup(\'category\')">By category</button>' +
        '</div>' +
        '<button class="btn btn-salmon btn-block mb-3" onclick="App.navigate(\'expense-new\')"><i class="bi bi-plus-circle"></i> Log new expense</button>' +
        '<div class="section-label">Ledger</div>' +
        '<div class="card p-3">' + (rows || '<div class="text-center py-4 text-muted">No expenses yet</div>') + '</div>';
    } else {
      const grouped = {};
      dateFiltered.forEach(e => {
        grouped[e.categoryId] = grouped[e.categoryId] || { items: [], total: 0 };
        grouped[e.categoryId].items.push(e);
        grouped[e.categoryId].total += e.amount;
      });
      const cats = Object.entries(grouped)
        .map(([cid, v]) => ({ id: cid, label: categoryById(cid)?.label || cid, icon: categoryById(cid)?.icon || 'bi-tag', ...v }))
        .sort((a, b) => b.total - a.total);

      const catHtml = cats.map(c =>
        '<div class="card p-3 mb-2">' +
          '<div class="d-flex align-items-center gap-2 mb-2">' +
            '<div class="ledger-icon expense" style="width:32px;height:32px;font-size:0.85rem"><i class="bi ' + c.icon + '"></i></div>' +
            '<div class="flex-grow-1 fw-700 text-teal-dark" style="font-size:var(--t-sm)">' + c.label + '</div>' +
            '<div class="fw-700 text-salmon">' + D.fmtR(c.total) + '</div>' +
          '</div>' +
          '<div style="height:6px;background:rgba(232,223,210,0.6);border-radius:6px;overflow:hidden">' +
            '<div style="height:100%;background:linear-gradient(90deg,var(--c-salmon),var(--c-salmon-dark));border-radius:6px;width:' + ((c.total / total) * 100) + '%"></div>' +
          '</div>' +
          '<div style="margin-top:4px;font-size:var(--t-xxs);color:var(--ac-warm-gray);font-weight:600">' + c.items.length + ' ' + (c.items.length === 1 ? 'entry' : 'entries') + '</div>' +
        '</div>'
      ).join('');      document.getElementById('expenseContent').innerHTML =
        renderDateRangePicker() +
        '<div class="card p-3 mb-3" style="border-left:4px solid var(--c-salmon)">' +
          '<div class="section-label" style="margin:0 0 4px">Expenses by category · ' + rangeLabel + '</div>' +
          '<div class="fs-2 fw-700 text-salmon">' + D.fmtR(total) + '</div>' +
          '<div class="text-muted fw-600" style="font-size:var(--t-xs)">' + dateFiltered.length + ' entries</div>' +
        '</div>' +
        '<div class="filter-tabs">' +
          '<button class="filter-tab ' + (expenseGroup === 'date' ? 'active' : '') + '" onclick="App.setExpenseGroup(\'date\')">By date</button>' +
          '<button class="filter-tab ' + (expenseGroup === 'category' ? 'active' : '') + '" onclick="App.setExpenseGroup(\'category\')">By category</button>' +
        '</div>' +
        '<button class="btn btn-salmon btn-block mb-3" onclick="App.navigate(\'expense-new\')"><i class="bi bi-plus-circle"></i> Log new expense</button>' +
        '<div>' + catHtml + '</div>';
      }
  }

  App.setExpenseGroup = function (g) { expenseGroup = g; renderExpenses(); };

  // ════════════════════════════════════════════════════════
  // NEW INVOICE FORM
  // ════════════════════════════════════════════════════════
  let invoiceFormStep = 1;
  let invoiceForm = {
    clientId: '', issueDate: '2026-05-15', dueDate: '2026-06-14',
    paymentTerms: 'Net 30', bankAccountId: 'ba_001',
    lineItems: [{ id: 'li-' + Date.now(), productId: '', description: '', qty: 0, unitPrice: 0 }],
    notes: '', sendNow: false,
  };

  function renderNewInvoiceForm() {
    const totalSteps = 4;
    const steps = ['Client', 'Items', 'Terms', 'Review'];

    const renderStep1 = () => {
      const clientChips = D.CLIENTS.map(c =>
        '<button class="client-chip ' + (invoiceForm.clientId === c.id ? 'selected' : '') + '" onclick="App.setInvoiceField(\'clientId\',\'' + c.id + '\')">' +
          '<div class="client-avatar">' + c.name[0] + '</div>' +
          '<div class="client-info"><div class="client-name">' + c.name + '</div><div class="client-type">' + c.type + '</div></div>' +
          (invoiceForm.clientId === c.id ? '<i class="bi bi-check-circle-fill" style="color:var(--c-lime-dark);font-size:1.3rem"></i>' : '') +
        '</button>'
      ).join('');
      return '<h5 class="form-title">Who is this invoice for?</h5>' +
        '<p class="form-sub">Select an existing client.</p>' +
        clientChips;
    };

    const renderStep2 = () => {
      const items = invoiceForm.lineItems.map((li, idx) => {
        const p = productById(li.productId);
        const prodOpts = D.PRODUCTS.map(p2 =>
          '<option value="' + p2.id + '" ' + (li.productId === p2.id ? 'selected' : '') + '>' + p2.label + ' (' + p2.stock + ' ' + p2.unit + ' in stock)</option>'
        ).join('');
        return '<div class="card p-3 mb-3" style="background:var(--ac-sand)">' +
          '<div class="d-flex justify-content-between align-items-center mb-2">' +
            '<span class="fw-700 text-teal" style="font-size:var(--t-xs);text-transform:uppercase;letter-spacing:0.08em">Item ' + (idx + 1) + '</span>' +
            (invoiceForm.lineItems.length > 1 ? '<button class="btn btn-sm btn-ghost" onclick="App.removeInvoiceItem(' + idx + ')"><i class="bi bi-x-lg"></i></button>' : '') +
          '</div>' +
          '<div class="mb-2"><label class="form-label">Product <span class="text-salmon">*</span></label>' +
            '<select class="form-select" onchange="App.updateInvoiceItem(' + idx + ',\'productId\',this.value)"><option value="">— Select a product —</option>' + prodOpts + '</select></div>' +
          '<div class="mb-2"><label class="form-label">Description</label>' +
            '<input class="form-control" value="' + li.description + '" onchange="App.updateInvoiceItem(' + idx + ',\'description\',this.value)" placeholder="Optional detail..."></div>' +
          '<div class="row g-2">' +
            '<div class="col-6"><label class="form-label">Qty ' + (p ? '(' + p.unit + ')' : '') + ' <span class="text-salmon">*</span></label>' +
              '<input type="number" class="form-control" value="' + (li.qty || '') + '" onchange="App.updateInvoiceItem(' + idx + ',\'qty\',parseFloat(this.value)||0)" placeholder="0"></div>' +
            '<div class="col-6"><label class="form-label">Unit price (R)</label>' +
              '<input type="number" class="form-control" value="' + (li.unitPrice || '') + '" onchange="App.updateInvoiceItem(' + idx + ',\'unitPrice\',parseFloat(this.value)||0)" placeholder="0.00" step="0.01"></div>' +
          '</div>' +
          '<div class="d-flex justify-content-between align-items-center pt-2 mt-2" style="border-top:1px solid rgba(232,223,210,0.9)">' +
            '<span class="text-muted" style="font-size:var(--t-xs)">Line total</span>' +
            '<span class="fw-700">' + D.fmtR(li.qty * li.unitPrice) + '</span>' +
          '</div>' +
        '</div>';
      }).join('');

      const subtotal = invoiceForm.lineItems.reduce((s, li) => s + (li.qty * li.unitPrice), 0);

      return '<h5 class="form-title">What are you invoicing for?</h5><p class="form-sub">Add the products and quantities.</p>' +
        items +
        '<button class="btn btn-ghost btn-block mb-3" onclick="App.addInvoiceItem()"><i class="bi bi-plus-circle"></i> Add another item</button>' +
        '<div class="card p-3" style="background:linear-gradient(135deg,var(--c-teal-dark),var(--c-teal));color:#fff">' +
          '<div class="d-flex justify-content-between fw-700"><span>Subtotal</span><span>' + D.fmtR(subtotal) + '</span></div>' +
        '</div>';
    };

    const renderStep3 = () => {
      const terms = ['On receipt', 'Net 7', 'Net 14', 'Net 30', 'Custom'];
      const termChips = terms.map(t =>
        '<button class="btn btn-sm ' + (invoiceForm.paymentTerms === t ? 'btn-teal' : 'btn-ghost') + '" onclick="App.setInvoiceField(\'paymentTerms\',\'' + t + '\')">' + t + '</button>'
      ).join('');

      const bankPicks = accounts.map(a =>
        '<div class="d-flex align-items-center gap-2 p-2 mb-1 rounded" style="background:var(--ac-sand);border:1.5px solid ' + (invoiceForm.bankAccountId === a.id ? 'var(--c-teal)' : 'transparent') + ';cursor:pointer" onclick="App.setInvoiceField(\'bankAccountId\',\'' + a.id + '\')">' +
          '<div style="width:36px;height:36px;border-radius:10px;background:rgba(47,111,122,0.12);color:var(--c-teal);display:flex;align-items:center;justify-content:center"><i class="bi bi-bank2"></i></div>' +
          '<div class="flex-grow-1"><div class="fw-700 text-teal-dark" style="font-size:var(--t-sm)">' + a.bank + (a.isPrimary ? ' <span class="badge bg-lime">Primary</span>' : '') + '</div>' +
            '<div style="font-size:var(--t-xs);color:var(--ac-warm-gray);font-weight:600">' + a.name + ' · ' + a.accountNumber + '</div></div>' +
          (invoiceForm.bankAccountId === a.id ? '<i class="bi bi-check-circle-fill text-teal"></i>' : '') +
        '</div>'
      ).join('');

      return '<h5 class="form-title">When is payment due?</h5><p class="form-sub">Set dates, terms, and bank account.</p>' +
        '<div class="row g-2 mb-2">' +
          '<div class="col-6"><label class="form-label">Issue date <span class="text-salmon">*</span></label>' +
            '<input type="date" class="form-control" value="' + invoiceForm.issueDate + '" onchange="App.setInvoiceField(\'issueDate\',this.value)"></div>' +
          '<div class="col-6"><label class="form-label">Due date</label>' +
            '<input type="date" class="form-control" value="' + invoiceForm.dueDate + '" onchange="App.setInvoiceField(\'dueDate\',this.value)"></div>' +
        '</div>' +
        '<div class="mb-2"><label class="form-label">Payment terms</label><div class="d-flex gap-1 flex-wrap">' + termChips + '</div></div>' +
        '<div class="mb-2"><label class="form-label">Pay into</label>' + bankPicks + '</div>' +
        '<div class="mb-2"><label class="form-label">Notes</label><textarea class="form-control" rows="2" onchange="App.setInvoiceField(\'notes\',this.value)" placeholder="Delivery instructions...">' + invoiceForm.notes + '</textarea></div>';
    };

    const renderStep4 = () => {
      const client = clientById(invoiceForm.clientId);
      const subtotal = invoiceForm.lineItems.reduce((s, li) => s + (li.qty * li.unitPrice), 0);
      const liReview = invoiceForm.lineItems.map((li, idx) => {
        const p = productById(li.productId);
        return '<div class="d-flex justify-content-between py-2" style="border-bottom:1px solid rgba(232,223,210,0.9)">' +
          '<div><div class="fw-700 text-teal-dark" style="font-size:var(--t-sm)">' + (p ? p.label : 'Item ' + (idx + 1)) + '</div>' +
            '<div style="font-size:var(--t-xs);color:var(--ac-warm-gray);font-weight:600">' + li.qty + ' ' + (p ? p.unit : '') + ' × ' + D.fmtR(li.unitPrice) + '</div></div>' +
          '<div class="fw-700">' + D.fmtR(li.qty * li.unitPrice) + '</div>' +
        '</div>';
      }).join('');

      return '<h5 class="form-title">Review & send</h5><p class="form-sub">Check the details before saving.</p>' +
        '<div class="card p-3 mb-3" style="background:var(--ac-sand)">' +
          '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Client</span><span class="fw-700 text-teal-dark">' + (client ? client.name : '—') + '</span></div>' +
          '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Issue date</span><span class="fw-700 text-teal-dark">' + D.fmtDate(invoiceForm.issueDate) + '</span></div>' +
          '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Due date</span><span class="fw-700 text-teal-dark">' + D.fmtDate(invoiceForm.dueDate) + '</span></div>' +
          '<div class="d-flex justify-content-between py-1"><span class="text-muted fw-600">Terms</span><span class="fw-700 text-teal-dark">' + invoiceForm.paymentTerms + '</span></div>' +
        '</div>' +
        '<div class="section-label">Line items</div>' + liReview +
        '<div class="d-flex justify-content-between py-2" style="border-top:2px solid rgba(47,111,122,0.15)">' +
          '<span class="fw-700 text-teal-dark">Total</span><span class="fw-700" style="font-size:var(--t-lg);color:var(--c-teal-dark)">' + D.fmtR(subtotal) + '</span>' +
        '</div>';
    };

    const stepContent = [null, renderStep1, renderStep2, renderStep3, renderStep4][invoiceFormStep]();

    const canContinue = (() => {
      if (invoiceFormStep === 1) return !!invoiceForm.clientId;
      if (invoiceFormStep === 2) return invoiceForm.lineItems.every(li => li.productId && li.qty > 0);
      if (invoiceFormStep === 3) return !!invoiceForm.issueDate;
      return true;
    })();

    document.getElementById('invoiceNewContent').innerHTML =
      '<div class="card p-3 mb-3">' +
        '<div class="d-flex justify-content-between mb-1">' +
          '<span class="fw-700 text-muted" style="font-size:var(--t-xs);text-transform:uppercase;letter-spacing:0.08em">' + steps[invoiceFormStep - 1] + '</span>' +
          '<span class="fw-700 text-teal" style="font-size:var(--t-xs)">' + invoiceFormStep + '/' + totalSteps + '</span>' +
        '</div>' +
        '<div style="height:5px;background:var(--ac-sand-dark);border-radius:3px;overflow:hidden">' +
          '<div style="height:100%;background:linear-gradient(90deg,var(--c-teal),var(--c-lime));border-radius:3px;width:' + ((invoiceFormStep / totalSteps) * 100) + '%"></div>' +
        '</div>' +
      '</div>' +
      '<div class="form-card">' + stepContent + '</div>' +
      '<div class="d-flex flex-column gap-2">' +
        (invoiceFormStep < totalSteps
          ? '<button class="btn btn-teal btn-block" ' + (!canContinue ? 'disabled' : '') + ' onclick="App.nextInvoiceStep()">Continue <i class="bi bi-arrow-right"></i></button>'
          : '<div class="d-flex gap-2">' +
              '<button class="btn btn-ghost flex-grow-1" onclick="App.saveInvoice(false)">Save as draft</button>' +
              '<button class="btn btn-lime flex-grow-1" onclick="App.saveInvoice(true)"><i class="bi bi-check-lg"></i> Create invoice</button>' +
            '</div>'
        ) +
      '</div>';
  }

  App.setInvoiceField = function (key, value) { invoiceForm[key] = value; renderNewInvoiceForm(); };
  App.nextInvoiceStep = function () { invoiceFormStep = Math.min(4, invoiceFormStep + 1); renderNewInvoiceForm(); };
  App.addInvoiceItem = function () {
    invoiceForm.lineItems.push({ id: 'li-' + Date.now(), productId: '', description: '', qty: 0, unitPrice: 0 });
    renderNewInvoiceForm();
  };
  App.removeInvoiceItem = function (idx) {
    if (invoiceForm.lineItems.length > 1) {
      invoiceForm.lineItems.splice(idx, 1);
      renderNewInvoiceForm();
    }
  };
  App.updateInvoiceItem = function (idx, key, value) {
    if (key === 'productId') {
      const p = productById(value);
      invoiceForm.lineItems[idx].productId = value;
      if (p) { invoiceForm.lineItems[idx].unitPrice = p.price; }
    } else {
      invoiceForm.lineItems[idx][key] = value;
    }
    renderNewInvoiceForm();
  };

  App.saveInvoice = function (sendNow) {
    const newInv = {
      id: nextInvoiceId(),
      clientId: invoiceForm.clientId,
      issueDate: invoiceForm.issueDate,
      dueDate: invoiceForm.dueDate,
      status: sendNow ? 'sent' : 'draft',
      bankAccountId: invoiceForm.bankAccountId,
      paymentTerms: invoiceForm.paymentTerms,
      lineItems: invoiceForm.lineItems.map((li, i) => ({ ...li, id: 'li-' + Date.now() + '-' + i })),
      notes: invoiceForm.notes || '',
      paidLineItemIds: [],
      attachments: [],
      linkedIncomeIds: [],
    };
    invoices.unshift(newInv);
    saveState();
    showToast(sendNow ? 'Invoice sent' : 'Invoice saved', newInv.id + ' · ' + D.fmtR(invoiceForm.lineItems.reduce((s, li) => s + (li.qty * li.unitPrice), 0)));
    // Reset form
    invoiceFormStep = 1;
    invoiceForm = {
      clientId: '', issueDate: '2026-05-15', dueDate: '2026-06-14',
      paymentTerms: 'Net 30', bankAccountId: 'ba_001',
      lineItems: [{ id: 'li-' + Date.now(), productId: '', description: '', qty: 0, unitPrice: 0 }],
      notes: '', sendNow: false,
    };
    navigate('invoice-detail', { invoiceId: newInv.id });
  };

  // ════════════════════════════════════════════════════════
  // NEW INCOME FORM
  // ════════════════════════════════════════════════════════
  function renderNewIncomeForm() {
    document.getElementById('incomeNewContent').innerHTML =
      '<div class="form-card">' +
        '<h5 class="form-title">Log income</h5><p class="form-sub">Record money received.</p>' +
        '<div class="mb-3"><label class="form-label">Client</label>' +
          '<select class="form-select" id="incClient"><option value="">— Walk-in —</option>' +
            D.CLIENTS.map(c => '<option value="' + c.id + '">' + c.name + '</option>').join('') +
          '</select></div>' +
        '<div class="mb-3"><label class="form-label">Product <span class="text-salmon">*</span></label>' +
          '<div class="row g-2">' + D.PRODUCTS.map(p =>
            '<div class="col-4"><div class="card p-2 text-center" style="cursor:pointer;border:1.5px solid transparent" onclick="this.style.borderColor=\'var(--c-lime)\';document.getElementById(\'incProd\').value=\'' + p.id + '\'">' +
              '<div class="fw-700 text-teal-dark" style="font-size:var(--t-xs)">' + p.label + '</div>' +
              '<div style="font-size:0.65rem;color:var(--ac-warm-gray)">' + D.fmtR(p.price) + '/' + p.unit + '</div></div></div>'
          ).join('') + '</div>' +
          '<input type="hidden" id="incProd"></div>' +
        '<div class="row g-2 mb-3">' +
          '<div class="col-6"><label class="form-label">Amount (R) <span class="text-salmon">*</span></label>' +
            '<input type="number" class="form-control" id="incAmount" placeholder="0.00" step="0.01"></div>' +
          '<div class="col-6"><label class="form-label">Date</label>' +
            '<input type="date" class="form-control" id="incDate" value="2026-05-15"></div>' +
        '</div>' +
        '<div class="mb-3"><label class="form-label">Payment method</label>' +
          '<select class="form-select" id="incMethod"><option value="eft">EFT</option><option value="cash">Cash</option><option value="card">Card</option><option value="mobile">Mobile</option></select></div>' +
        '<div class="mb-3"><label class="form-label">Bank account</label>' +
          '<select class="form-select" id="incBank">' + accounts.map(a => '<option value="' + a.id + '">' + a.bank + ' ' + a.accountNumber + '</option>').join('') + '</select></div>' +
        '<div class="mb-3"><label class="form-label">Note</label><input type="text" class="form-control" id="incNote" placeholder="Optional..."></div>' +
      '</div>' +
      '<button class="btn btn-lime btn-block" onclick="App.submitIncome()"><i class="bi bi-check-lg"></i> Log income</button>';
  }

  App.submitIncome = function () {
    const amount = parseFloat(document.getElementById('incAmount').value);
    const productId = document.getElementById('incProd').value;
    if (!amount || amount <= 0 || !productId) {
      showToast('Error', 'Please fill in amount and product', 'error');
      return;
    }
    const newInc = {
      id: 'inc_' + Date.now(),
      date: document.getElementById('incDate').value,
      source: 'standalone', invoiceId: null,
      clientId: document.getElementById('incClient').value || null,
      productId: productId,
      amount: amount,
      bankAccountId: document.getElementById('incBank').value,
      method: document.getElementById('incMethod').value,
      note: document.getElementById('incNote').value || '',
    };
    incomeEntries.unshift(newInc);
    const acct = accounts.find(a => a.id === newInc.bankAccountId);
    if (acct) acct.balance += amount;
    transactions.unshift({
      id: 't_' + Date.now(), date: newInc.date, kind: 'in', amount,
      accountId: newInc.bankAccountId,
      label: 'Direct sale — ' + (productById(productId)?.label || ''),
      ref: newInc.id,
    });
    saveState();
    showToast('Income logged', D.fmtR(amount) + ' recorded');
    navigate('income');
  };

  // ════════════════════════════════════════════════════════
  // NEW EXPENSE FORM
  // ════════════════════════════════════════════════════════
  function renderNewExpenseForm() {      const catChips = D.EXPENSE_CATEGORIES.map(c =>
      '<div class="card cat-chip p-2 text-center" style="cursor:pointer;border:1.5px solid transparent" onclick="document.querySelectorAll(\'.cat-chip\').forEach(el=>{el.style.borderColor=\'transparent\'});this.style.borderColor=\'var(--c-salmon)\';document.getElementById(\'expCat\').value=\'' + c.id + '\'">' +
        '<div class="cat-chip">' +
          '<div style="width:32px;height:32px;border-radius:10px;background:rgba(239,128,112,0.14);color:var(--c-salmon-dark);display:flex;align-items:center;justify-content:center;margin:0 auto"><i class="bi ' + c.icon + '"></i></div>' +
          '<div class="fw-700 text-teal-dark" style="font-size:0.68rem;margin-top:4px;line-height:1.2">' + c.label + '</div>' +
        '</div>' +
      '</div>'
    ).join('');

    document.getElementById('expenseNewContent').innerHTML =
      '<div class="form-card">' +
        '<h5 class="form-title">Log expense</h5><p class="form-sub">Record money spent.</p>' +
        '<div class="mb-3"><label class="form-label">Category <span class="text-salmon">*</span></label>' +
          '<div class="row g-2">' + catChips + '</div>' +
          '<input type="hidden" id="expCat"></div>' +
        '<div class="mb-3"><label class="form-label">Amount (R) <span class="text-salmon">*</span></label>' +
          '<input type="number" class="form-control" id="expAmount" placeholder="0.00" step="0.01"></div>' +
        '<div class="row g-2 mb-3">' +
          '<div class="col-6"><label class="form-label">Date</label><input type="date" class="form-control" id="expDate" value="2026-05-15"></div>' +
          '<div class="col-6"><label class="form-label">Paid from</label><select class="form-select" id="expBank">' +
            accounts.map(a => '<option value="' + a.id + '">' + a.bank + ' ' + a.accountNumber + '</option>').join('') +
          '</select></div>' +
        '</div>' +
        '<div class="mb-3"><label class="form-label">Vendor</label><input type="text" class="form-control" id="expVendor" placeholder="Paid to..."></div>' +
        '<div class="mb-3"><label class="form-label">Note</label><textarea class="form-control" id="expNote" rows="2" placeholder="What was it for..."></textarea></div>' +
      '</div>' +
      '<button class="btn btn-salmon btn-block" onclick="App.submitExpense()"><i class="bi bi-check-lg"></i> Log expense</button>';
  }

  App.submitExpense = function () {
    const catId = document.getElementById('expCat').value;
    const amount = parseFloat(document.getElementById('expAmount').value);
    if (!catId || !amount || amount <= 0) {
      showToast('Error', 'Please fill in category and amount', 'error');
      return;
    }
    const newExp = {
      id: 'exp_' + Date.now(),
      date: document.getElementById('expDate').value,
      categoryId: catId,
      amount: amount,
      bankAccountId: document.getElementById('expBank').value,
      vendor: document.getElementById('expVendor').value || '',
      note: document.getElementById('expNote').value || '',
    };
    expenseEntries.unshift(newExp);
    const acct = accounts.find(a => a.id === newExp.bankAccountId);
    if (acct) acct.balance -= amount;
    transactions.unshift({
      id: 't_' + Date.now(), date: newExp.date, kind: 'out', amount,
      accountId: newExp.bankAccountId,
      label: newExp.vendor || categoryById(catId)?.label || 'Expense',
      ref: newExp.id,
    });
    saveState();
    showToast('Expense logged', D.fmtR(amount) + ' — ' + (categoryById(catId)?.label || ''));
    navigate('expense');
  };

  // ════════════════════════════════════════════════════════
  // INITIALIZATION
  // ════════════════════════════════════════════════════════
  function init() {
    initState();

    // Back button handler
    document.querySelectorAll('.back-btn').forEach(btn => {
      btn.addEventListener('click', goBack);
    });

    // Tab bar navigation
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', function () {
        const page = this.dataset.page;
        if (page) navigate(page);
      });
    });

    // Initial render
    navigate('hub');

    // Show boot screen removal
    setTimeout(() => {
      const boot = document.getElementById('boot');
      if (boot) {
        boot.classList.add('opacity-0');
        setTimeout(() => boot.remove(), 500);
      }
    }, 400);
  }

  App.navigate = navigate;
  App.goBack = goBack;
  App.D = D;
  App.showToast = showToast;
  App.resetToSeed = resetToSeed;
  App.openReconcile = openReconcile;
  App.closeReconcile = closeReconcile;
  App.reconcileMatch = reconcileMatch;
  App.dismissStatement = dismissStatement;
  App.captureStatementAsIncome = captureStatementAsIncome;
  App.captureStatementAsExpense = captureStatementAsExpense;

  // ── Date range API ────────────────────────────────────
  App.setDateRange = function(preset) {
    if (preset === 'custom') {
      dateRange.preset = 'custom';
      renderCurrentView();
      return;
    }
    const range = getDateRangeForPreset(preset);
    applyDateRange(preset, range.startDate, range.endDate);
  };

  App.applyCustomDateRange = function() {
    const start = document.getElementById('drStart')?.value || null;
    const end = document.getElementById('drEnd')?.value || null;
    if (start && end && start > end) {
      App.showToast('Invalid range', 'Start date must be before end date', 'error');
      return;
    }
    applyDateRange('custom', start, end);
  };

  // ── Expose formats ──
  App.fmtR = D.fmtR;
  App.fmtDate = D.fmtDate;
  App.fmtDateShort = D.fmtDateShort;

  // ── Start ──
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
