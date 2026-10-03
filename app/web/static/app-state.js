// ═══════════════════════════════════════════════════════════════════
// STATE: what more than one screen reads
// ═══════════════════════════════════════════════════════════════════
//
// Who is signed in and what the account may reach, this tab's current
// customer, the customer page on screen, and the customer lists the overview
// and the customer list loaded. Each value is changed here, through the
// setter beside it, and read anywhere: no script assigns another script's
// variable, and nothing is kept on window.

// ── The signed-in account ────────────────────────────────────────────────────
// Authentication is cookie-only in the browser. The HttpOnly tokens cannot
// be read by injected JavaScript and do not survive in localStorage dumps.
var _currentUser = null;

// Paths the server keeps open without the write capability. Sent by /auth/me
// rather than restated here — a second copy of the rule is the one that goes
// stale, and it would go stale in the direction of offering something the
// server refuses.
var _writeExempt = [];

// What this account reaches, resolved by the server. The interface holds no
// copy of the rules — it hides what is not in these lists, so a screen cannot
// drift from the route it leads to.
var _features = [];
var _modules = [];
var _allowedViews = [];

// /auth/me answers {user: {...}, features, modules, views, write_exempt}.
function setSession(me) {
  // Storing the envelope meant every read of _currentUser.role and
  // _currentUser.display_name was undefined, so the avatar has been showing
  // "?" for as long as it has existed.
  _currentUser = me.user || me;
  if (me.write_exempt) _writeExempt = me.write_exempt;
  _features = me.features || [];
  _modules = me.modules || [];
  _allowedViews = me.views || [];
}

function setCurrentUser(user) {
  _currentUser = user;
}

// ── Read-only accounts ───────────────────────────────────────────────────────
// The server decides; this only stops the interface offering what it will
// refuse. Anything marked data-write is hidden without the capability, and a
// badge says why rather than leaving someone hunting for a menu that is gone.
function canWrite() {
  return !!(_currentUser && _currentUser.can_write);
}

// The second, stricter tier. tenant_write is what lets a control change a
// customer's Microsoft tenant (policy deploy/enforce/restore, consent). The
// server checks it separately via require_tenant_write, and it implies
// can_write — so a control marked data-write="tenant" needs both.
function canTenantWrite() {
  return !!(_currentUser && _currentUser.tenant_write);
}

function hasFeature(key) {
  // Empty until /auth/me answers. Hiding everything for that instant is the
  // right way round: showing a control and taking it away reads as a bug, and
  // offering one that will 403 reads as a broken tool.
  return _features.indexOf(key) !== -1;
}

function hasModule(key) {
  return _modules.indexOf(key) !== -1;
}

function canOpenView(name) {
  return _allowedViews.indexOf(name) !== -1;
}

// ── The current customer ────────────────────────────────────────────────────
// The server keeps no "active customer": every call made for a customer names
// it. What is left of the idea lives here, in the browser, per tab:
//
//   * the current customer is the one whose page this tab opened last. The
//     customer page always uses its own id (_custPage.id); the tools that act
//     on one customer at a time (Nettverk's devices and audit, the FortiGate
//     form, provisioning, the Sybrt console, pentest's segmentation test)
//     default to this one and say which customer it is.
//   * it is kept in sessionStorage, which is per tab: a second tab on another
//     customer changes nothing here. A tab opened fresh starts from the most
//     recent customer in Nylige.
//   * Nylige (the palette's recent customers) is the last five customers
//     opened in any tab, in localStorage.
//
// A per-user selection on the server was shared by every tab of that user,
// so opening customer B in one tab made the next note, audit or report in the
// other tab land on B.
var _tabCustomerId = null;

function currentCustomerId() {
  if (_tabCustomerId) return _tabCustomerId;
  try {
    _tabCustomerId = sessionStorage.getItem('sybr_tab_customer')
      || JSON.parse(localStorage.getItem('sybr_recent_customers') || '[]')[0] || null;
  } catch (e) { _tabCustomerId = null; }
  return _tabCustomerId;
}

function setCurrentCustomer(customerId) {
  _tabCustomerId = customerId || null;
  try {
    if (customerId) sessionStorage.setItem('sybr_tab_customer', customerId);
    else sessionStorage.removeItem('sybr_tab_customer');
    if (!customerId) return;
    var recent = JSON.parse(localStorage.getItem('sybr_recent_customers') || '[]');
    recent = recent.filter(function(id) { return id !== customerId; });
    recent.unshift(customerId);
    localStorage.setItem('sybr_recent_customers', JSON.stringify(recent.slice(0, 5)));
  } catch (e) { /* private mode: the tab still remembers it until reload */ }
}

// ── The customer page ───────────────────────────────────────────────────────
// Which customer the page shows, its record once loaded, the tab and sub-tab
// on screen and which tabs have loaded (app-customer-detail.js). Every call
// the page and its tabs make names this customer (_custPage.id).
var _custPage = {id: null, cust: null, tab: 'funn', sub: '', loaded: {}};

function setCustPage(page) {
  _custPage = page;
}

// ── Customer lists ──────────────────────────────────────────────────────────
// The dashboard's per-customer overview ({customers: [...]}), loaded by
// Oversikt, the customer page, the palette and the UniFi sub-site view; null
// until one of them has.
var _overviewData = null;

function setOverviewData(data) {
  _overviewData = data;
}

// The customer registry (/api/customers), loaded by Kunder and the tools'
// customer bars.
var _allCustomers = [];

function setAllCustomers(list) {
  _allCustomers = list;
}
