/* ============================================================
   AvoConnect — My Finances Seed Data
   All business data for the demo app
   ============================================================ */

const FinanceData = (() => {
  const BUSINESS = {
    id: 'biz_001',
    name: 'Nala Charcoal Co-op',
    initial: 'N',
    province: 'Limpopo',
    email: 'nala.coop@example.co.za',
    location: 'Polokwane',
  };

  const PRODUCTS = [
    { id: 'p_charcoal',  label: 'Charcoal',       unit: 'kg', price: 22.00, stock: 1840 },
    { id: 'p_firewood',  label: 'Firewood',       unit: 'kg', price: 6.50,  stock: 3200 },
    { id: 'p_biochar',   label: 'Biochar',        unit: 'kg', price: 35.00, stock: 420 },
    { id: 'p_briquette', label: 'Briquettes',     unit: 'kg', price: 18.00, stock: 960 },
    { id: 'p_feed',      label: 'Animal Feed',    unit: 'kg', price: 14.00, stock: 750 },
    { id: 'p_potato',    label: 'Potatoes',       unit: 'kg', price: 12.00, stock: 1200 },
  ];

  const CLIENTS = [
    { id: 'c_001', name: 'Polokwane Market', type: 'Market',     contact: '015 290 2000' },
    { id: 'c_002', name: 'Greenfields Lodge', type: 'Wholesale',  contact: 'orders@greenfields.co.za' },
    { id: 'c_003', name: 'Mokopane Spar',     type: 'Retail',     contact: '015 491 8200' },
    { id: 'c_004', name: 'Thabo Mahlangu',    type: 'Individual', contact: '082 555 1212' },
    { id: 'c_005', name: 'BraaiHouse Group',  type: 'Wholesale',  contact: 'procurement@braaihouse.co.za' },
  ];

  const BANK_ACCOUNTS = [
    { id: 'ba_001', bank: 'FNB',       name: 'Business Cheque', accountNumber: '•••• 4421', holder: 'Nala Charcoal Co-op', balance: 18420.55, currency: 'ZAR', isPrimary: true,  color: '#2f6f7a' },
    { id: 'ba_002', bank: 'Capitec',    name: 'Savings',         accountNumber: '•••• 9087', holder: 'Nala Charcoal Co-op', balance: 6210.00,  currency: 'ZAR', isPrimary: false, color: '#a2cc39' },
    { id: 'ba_003', bank: 'Cash on hand', name: 'Petty cash',   accountNumber: '—',          holder: 'Operations',         balance: 1240.00,  currency: 'ZAR', isPrimary: false, color: '#ef8070' },
  ];

  const INVOICES = [
    {
      id: 'INV-2026-0014', clientId: 'c_002', issueDate: '2026-05-12', dueDate: '2026-06-11',
      status: 'sent', bankAccountId: 'ba_001', paymentTerms: 'Net 30',
      lineItems: [
        { id: 'li1', productId: 'p_charcoal',  description: 'Lumpwood charcoal 25kg bags', qty: 60,  unit: 'kg', unitPrice: 22.00 },
        { id: 'li2', productId: 'p_briquette', description: 'Briquettes for restaurant',   qty: 40,  unit: 'kg', unitPrice: 18.00 },
      ],
      notes: 'Delivery to lodge kitchen on Tue 19 May.', paidAmount: 0, paidLineItemIds: [], linkedIncomeIds: [],
    },
    {
      id: 'INV-2026-0013', clientId: 'c_001', issueDate: '2026-05-08', dueDate: '2026-05-22',
      status: 'partial', bankAccountId: 'ba_001', paymentTerms: 'Net 14',
      lineItems: [
        { id: 'li1', productId: 'p_charcoal', description: 'Bulk charcoal',  qty: 120, unit: 'kg', unitPrice: 22.00 },
        { id: 'li2', productId: 'p_potato',   description: 'Potato bags',    qty: 80,  unit: 'kg', unitPrice: 12.00 },
      ],
      notes: '', paidAmount: 1800.00, paidLineItemIds: ['li1'], linkedIncomeIds: ['inc_006'],
    },
    {
      id: 'INV-2026-0012', clientId: 'c_005', issueDate: '2026-04-29', dueDate: '2026-05-13',
      status: 'overdue', bankAccountId: 'ba_001', paymentTerms: 'Net 14',
      lineItems: [
        { id: 'li1', productId: 'p_charcoal', description: 'Charcoal supply',  qty: 200, unit: 'kg', unitPrice: 22.00 },
      ],
      notes: 'Followed up by SMS 14 May.', paidAmount: 0, paidLineItemIds: [], linkedIncomeIds: [],
    },
    {
      id: 'INV-2026-0011', clientId: 'c_003', issueDate: '2026-04-24', dueDate: '2026-05-08',
      status: 'paid', bankAccountId: 'ba_001', paymentTerms: 'Net 14',
      lineItems: [
        { id: 'li1', productId: 'p_firewood',  description: 'Firewood bundles',  qty: 240, unit: 'kg', unitPrice: 6.50 },
        { id: 'li2', productId: 'p_biochar',   description: 'Garden biochar',    qty: 30,  unit: 'kg', unitPrice: 35.00 },
      ],
      notes: '', paidAmount: 2610.00, paidLineItemIds: ['li1','li2'], linkedIncomeIds: ['inc_004'],
    },
    {
      id: 'INV-2026-0010', clientId: 'c_004', issueDate: '2026-05-02', dueDate: null,
      status: 'draft', bankAccountId: 'ba_001', paymentTerms: 'On receipt',
      lineItems: [
        { id: 'li1', productId: 'p_firewood', description: '', qty: 50, unit: 'kg', unitPrice: 6.50 },
      ],
      notes: '', paidAmount: 0, paidLineItemIds: [], linkedIncomeIds: [],
    },
  ];

  const INCOME = [
    { id: 'inc_001', date: '2026-05-15', source: 'standalone', invoiceId: null, clientId: 'c_004', productId: 'p_firewood', qty: 25, unit: 'kg', amount: 162.50, bankAccountId: 'ba_003', method: 'cash', note: 'Walk-in sale at gate' },
    { id: 'inc_002', date: '2026-05-14', source: 'standalone', invoiceId: null, clientId: 'c_001', productId: 'p_potato',   qty: 40, unit: 'kg', amount: 480.00, bankAccountId: 'ba_001', method: 'eft', note: '' },
    { id: 'inc_003', date: '2026-05-13', source: 'standalone', invoiceId: null, clientId: 'c_004', productId: 'p_charcoal', qty: 12, unit: 'kg', amount: 264.00, bankAccountId: 'ba_003', method: 'cash', note: '' },
    { id: 'inc_004', date: '2026-05-08', source: 'invoice',   invoiceId: 'INV-2026-0011', clientId: 'c_003', productId: null, qty: null, unit: null, amount: 2610.00, bankAccountId: 'ba_001', method: 'eft', note: 'Mokopane Spar — paid in full' },
    { id: 'inc_005', date: '2026-05-05', source: 'standalone', invoiceId: null, clientId: 'c_002', productId: 'p_biochar', qty: 15, unit: 'kg', amount: 525.00, bankAccountId: 'ba_002', method: 'eft', note: '' },
    { id: 'inc_006', date: '2026-05-10', source: 'invoice',   invoiceId: 'INV-2026-0013', clientId: 'c_001', productId: null, qty: null, unit: null, amount: 1800.00, bankAccountId: 'ba_001', method: 'eft', note: 'Polokwane Market — first instalment' },
  ];

  const EXPENSE_CATEGORIES = [
    { id: 'machinery_equipment',       label: 'Machinery & equipment', icon: 'bi-wrench-adjustable' },
    { id: 'labour_monthly',            label: 'Monthly wages',         icon: 'bi-people' },
    { id: 'labour_delivery',           label: 'Delivery wages',        icon: 'bi-truck' },
    { id: 'labour_parttime',           label: 'Part-time wages',       icon: 'bi-person-workspace' },
    { id: 'fuel_energy',               label: 'Fuel & energy',         icon: 'bi-fuel-pump' },
    { id: 'packaging_storage',         label: 'Packaging & storage',   icon: 'bi-box-seam' },
    { id: 'transport_logistics',       label: 'Transport & logistics', icon: 'bi-truck-front' },
    { id: 'safety_health_environment', label: 'Safety, health & env.', icon: 'bi-shield-check' },
    { id: 'maintenance_repairs',       label: 'Maintenance & repairs', icon: 'bi-tools' },
    { id: 'raw_materials',             label: 'Raw materials',         icon: 'bi-tree' },
    { id: 'other_expenses',            label: 'Other',                 icon: 'bi-three-dots' },
  ];

  const EXPENSES = [
    { id: 'exp_001', date: '2026-05-15', categoryId: 'fuel_energy',         amount: 480.00,  bankAccountId: 'ba_001', vendor: 'Engen Polokwane',  note: 'Petrol for bakkie' },
    { id: 'exp_002', date: '2026-05-14', categoryId: 'labour_parttime',     amount: 1200.00, bankAccountId: 'ba_003', vendor: '4 part-time hires', note: 'Week 19 sorting & stacking' },
    { id: 'exp_003', date: '2026-05-13', categoryId: 'packaging_storage',   amount: 360.00,  bankAccountId: 'ba_001', vendor: 'BagsCo SA',         note: '25kg charcoal bags' },
    { id: 'exp_004', date: '2026-05-12', categoryId: 'maintenance_repairs', amount: 850.00,  bankAccountId: 'ba_001', vendor: 'Polokwane Welding', note: 'Kiln door repair' },
    { id: 'exp_005', date: '2026-05-09', categoryId: 'transport_logistics', amount: 1500.00, bankAccountId: 'ba_001', vendor: 'Mphahlele Transport', note: 'Lodge delivery run' },
    { id: 'exp_006', date: '2026-05-06', categoryId: 'safety_health_environment', amount: 620.00, bankAccountId: 'ba_002', vendor: 'SafetyMax', note: 'PPE — gloves & masks' },
    { id: 'exp_007', date: '2026-05-04', categoryId: 'raw_materials',       amount: 980.00,  bankAccountId: 'ba_001', vendor: 'Local biomass collector', note: '' },
    { id: 'exp_008', date: '2026-05-01', categoryId: 'labour_monthly',      amount: 6400.00, bankAccountId: 'ba_001', vendor: 'May wages', note: '' },
  ];

  const WEEKLY_CASHFLOW = [
    { week: 'W16', label: '13–19 Apr', moneyIn: 3200, moneyOut: 4100 },
    { week: 'W17', label: '20–26 Apr', moneyIn: 5400, moneyOut: 2900 },
    { week: 'W18', label: '27 Apr–3 May', moneyIn: 4800, moneyOut: 7300 },
    { week: 'W19', label: '4–10 May',  moneyIn: 6840, moneyOut: 3200 },
    { week: 'W20', label: '11–17 May', moneyIn: 4410, moneyOut: 4810 },
  ];

  const TRANSACTIONS = [
    { id: 't_001', date: '2026-05-15', kind: 'in',  amount: 162.50,  accountId: 'ba_003', label: 'Cash sale — Thabo M.',          ref: 'inc_001' },
    { id: 't_002', date: '2026-05-15', kind: 'out', amount: 480.00,  accountId: 'ba_001', label: 'Engen Polokwane (fuel)',         ref: 'exp_001' },
    { id: 't_003', date: '2026-05-14', kind: 'in',  amount: 480.00,  accountId: 'ba_001', label: 'Polokwane Market — potatoes',    ref: 'inc_002' },
    { id: 't_004', date: '2026-05-14', kind: 'out', amount: 1200.00, accountId: 'ba_003', label: 'Part-time wages — wk 19',        ref: 'exp_002' },
    { id: 't_005', date: '2026-05-13', kind: 'in',  amount: 264.00,  accountId: 'ba_003', label: 'Cash sale — Thabo M.',          ref: 'inc_003' },
    { id: 't_006', date: '2026-05-12', kind: 'out', amount: 850.00,  accountId: 'ba_001', label: 'Polokwane Welding (kiln)',       ref: 'exp_004' },
    { id: 't_007', date: '2026-05-10', kind: 'in',  amount: 1800.00, accountId: 'ba_001', label: 'INV-0013 instalment — Polokwane Market', ref: 'inc_006' },
    { id: 't_008', date: '2026-05-08', kind: 'in',  amount: 2610.00, accountId: 'ba_001', label: 'INV-0011 paid — Mokopane Spar', ref: 'inc_004' },
    { id: 't_009', date: '2026-05-06', kind: 'out', amount: 620.00,  accountId: 'ba_002', label: 'SafetyMax — PPE',                ref: 'exp_006' },
  ];

  const STATEMENT_ENTRIES = [
    { id: 'stmt_001', date: '2026-05-15', kind: 'in',  amount: 162.50,  accountId: 'ba_003', label: 'CASH DEPOSIT',              reference: 'Thabo Mahlangu' },
    { id: 'stmt_002', date: '2026-05-15', kind: 'out', amount: 480.00,  accountId: 'ba_001', label: 'DEBIT CARD PURCHASE',        reference: 'ENGEN POLOKWANE' },
    { id: 'stmt_003', date: '2026-05-14', kind: 'in',  amount: 480.00,  accountId: 'ba_001', label: 'EFT CREDIT',                 reference: 'Polokwane Market' },
    { id: 'stmt_004', date: '2026-05-12', kind: 'out', amount: 850.00,  accountId: 'ba_001', label: 'DEBIT CARD PURCHASE',        reference: 'Polokwane Welding' },
    { id: 'stmt_005', date: '2026-05-10', kind: 'in',  amount: 1800.00, accountId: 'ba_001', label: 'EFT CREDIT',                 reference: 'Polokwane Market' },
    { id: 'stmt_006', date: '2026-05-08', kind: 'in',  amount: 2610.00, accountId: 'ba_001', label: 'EFT CREDIT',                 reference: 'Mokopane Spar' },
    { id: 'stmt_007', date: '2026-05-06', kind: 'out', amount: 620.00,  accountId: 'ba_002', label: 'DEBIT CARD PURCHASE',        reference: 'SAFETYMAX' },
  ];

  // ── Helpers ──
  const fmtRShort = (n) => {
    if (n == null || isNaN(n)) return 'R —';
    if (Math.abs(n) >= 1000) return 'R ' + (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return 'R ' + Math.round(n).toLocaleString('en-ZA');
  };

  const fmtR = (n) => {
    if (n == null || isNaN(n)) return 'R —';
    return 'R ' + Number(n).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const fmtDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso + 'T00:00');
    return d.toLocaleDateString('en-ZA', { day: '2-digit', month: 'short', year: 'numeric' });
  };

  const fmtDateShort = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso + 'T00:00');
    return d.toLocaleDateString('en-ZA', { day: '2-digit', month: 'short' });
  };

  return {
    BUSINESS, PRODUCTS, CLIENTS, BANK_ACCOUNTS, INVOICES, INCOME,
    EXPENSE_CATEGORIES, EXPENSES, WEEKLY_CASHFLOW, TRANSACTIONS, STATEMENT_ENTRIES,
    fmtR, fmtRShort, fmtDate, fmtDateShort,
  };
})();
