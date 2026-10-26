// Order desk interactivity. One engine drives every filterable list (swing stocks, intraday stocks, signals):
// controls say which list they act on with data-target="#list-id", items carry their facts as data-* attributes.
// Everything runs on server-rendered rows; nothing here builds an order.
(() => {
  let refocusQty = false;   // set when the ticket's quantity changes, because the ticket re-renders
  const states = {};   // list id -> { filters, query, sort }; survives HTMX re-renders so a filter is not lost on a swap
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const stateFor = (list) => (states[list.id] ??= { filters: {}, query: '', sort: list.dataset.defaultSort });

  // numbers compare as numbers, everything else as text; `direction` is +1 or -1
  const compare = (key, direction) => (a, b) => {
    const [x, y] = [a.dataset[key] ?? '', b.dataset[key] ?? ''];
    const [nx, ny] = [parseFloat(x), parseFloat(y)];
    return direction * (Number.isNaN(nx) || Number.isNaN(ny) ? x.localeCompare(y) : nx - ny);
  };

  function syncControls(list, state, shown, total) {
    const mine = `[data-target="#${list.id}"]`;
    $$(`${mine}[data-filter]`).forEach((control) => {
      const active = state.filters[control.dataset.filter] ?? 'all';
      if (control.tagName === 'SELECT') control.value = active;
      else control.setAttribute('aria-pressed', String(active === control.dataset.value));
    });
    $$(`button${mine}[data-sort]`).forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.sort === state.sort)));
    $$(`select${mine}[data-sort]`).forEach((select) => { select.value = state.sort; });
    $$(`${mine}[data-search]`).forEach((input) => { input.value = state.query; });
    $$(`[data-count-for="#${list.id}"]`).forEach((text) => { text.textContent = `Showing ${shown} of ${total}`; });
  }

  // the intensity bar always shows whatever the list is currently ranked by
  function paintBars(items, key) {
    items.forEach((item) => {
      const bar = $('[data-bar]', item);
      if (!bar) return;
      const value = parseFloat(item.dataset[key]);
      bar.style.width = `${Number.isNaN(value) ? item.dataset.barDefault : value}%`;
      if ('short' in item.dataset) {   // intraday rows: green for buy intensity, red for short intensity
        bar.classList.toggle('bg-red-700', key === 'short');
        bar.classList.toggle('bg-green-700', key !== 'short');
      }
    });
  }

  function apply(list) {
    const state = stateFor(list);
    const items = [...list.children];
    let shown = 0;
    items.forEach((item) => {
      const visible = Object.entries(state.filters).every(([name, wanted]) => wanted === 'all' || item.dataset[name] === wanted)
        && (item.dataset.name ?? '').includes(state.query);
      item.hidden = !visible;
      shown += visible;
    });
    const [direction, key] = [state.sort.startsWith('-') ? -1 : 1, state.sort.slice(1)];
    items.sort(compare(key, direction)).forEach((item) => list.appendChild(item));
    paintBars(items, key);
    syncControls(list, state, shown, items.length);
  }

  function markSelected() {
    const symbol = $('#detail [data-symbol]')?.dataset.symbol;
    $$('a[data-tab]').forEach((tab) => {   // switching tabs keeps the stock you are looking at
      for (const attribute of ['href', 'hx-get']) {
        const url = new URL(tab.getAttribute(attribute), location.origin);
        if (symbol) url.searchParams.set('symbol', symbol);
        tab.setAttribute(attribute, url.pathname + url.search);
      }
      window.htmx?.process(tab);   // htmx reads hx-get once, so it must be told the link changed
    });
    $$('li[id^="row-"]').forEach((row) => {
      const button = $('button', row);
      if (row.id === `row-${symbol}`) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    });
  }

  // ---- phones: the detail is a pushed full-screen view (a native "stack" screen) ----
  const phone = matchMedia('(max-width: 1023.98px)');
  const deskRoot = () => $('#desk');

  // everything outside the open pane becomes inert (WCAG 2.4.3 / 2.1.2: focus can't wander behind it); dialogs stay usable
  function setBackgroundInert(on) {
    if (!on) { $$('[data-inert-by-pane]').forEach((el) => { el.inert = false; el.removeAttribute('data-inert-by-pane'); }); return; }
    for (let node = $('#detail'); node && node !== document.body; node = node.parentElement) {
      [...node.parentElement.children].forEach((sibling) => {
        if (sibling === node || sibling.tagName === 'DIALOG' || sibling.tagName === 'SCRIPT' || sibling.id === 'desk-status') return;
        sibling.inert = true;
        sibling.setAttribute('data-inert-by-pane', '');
      });
    }
  }

  function openDetail() {
    if (!phone.matches || !deskRoot()) return;
    deskRoot().setAttribute('data-detail-open', '');
    setBackgroundInert(true);
    $('#detail').scrollTop = 0;
    $('#sum-h')?.focus({ preventScroll: true });
  }

  function closeDetail() {
    if (!deskRoot()?.hasAttribute('data-detail-open')) return;
    deskRoot().removeAttribute('data-detail-open');
    setBackgroundInert(false);
    $('li[id^="row-"] button[aria-current="true"]')?.focus();   // back where the user came from
  }

  phone.addEventListener('change', closeDetail);   // rotating to a wide screen: the pane becomes a normal column again

  // status banners: open on desktop, folded to their headline on phones so the list starts near the top
  const syncDisclosures = () => $$('details[data-desktop-open]').forEach((card) => { card.open = !phone.matches; });

  function refreshAll() {
    $$('[data-default-sort]').forEach(apply);
    markSelected();
    $('#sizer')?.dispatchEvent(new Event('input'));   // suggested quantities for whatever is on screen now
  }

  // ---- controls ----
  const listFor = (control) => $(control.dataset.target);

  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-close-detail]')) { closeDetail(); return; }
    const button = event.target.closest('button[data-target]');
    const list = button && listFor(button);
    if (!list) return;
    const state = stateFor(list);
    if (button.dataset.filter) state.filters[button.dataset.filter] = button.dataset.value;
    else if (button.dataset.sort) state.sort = button.dataset.sort;
    else return;
    apply(list);
  });

  document.addEventListener('input', (event) => {
    const input = event.target.closest('input[data-search]');
    const list = input && listFor(input);
    if (!list) return;
    stateFor(list).query = input.value.trim().toLowerCase();
    apply(list);
  });

  document.addEventListener('change', (event) => {
    const select = event.target.closest('select[data-target]');
    const list = select && listFor(select);
    if (list) {
      const state = stateFor(list);
      if (select.dataset.filter) state.filters[select.dataset.filter] = select.value;
      else state.sort = select.value;
      apply(list);
    }
    if (event.target.id === 'ticket-qty') refocusQty = true;
  });

  // arrow keys step through the visible stocks, so the desk can be driven without a mouse
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !$('dialog[open]') && deskRoot()?.hasAttribute('data-detail-open')) { closeDetail(); return; }
    if (!['ArrowDown', 'ArrowUp'].includes(event.key) || !event.target.closest('li[id^="row-"]')) return;
    const rows = $$('li[id^="row-"]', event.target.closest('ul')).filter((row) => !row.hidden);
    const at = rows.indexOf(event.target.closest('li'));
    const next = rows[at + (event.key === 'ArrowDown' ? 1 : -1)];
    if (next) { event.preventDefault(); $('button', next).focus(); }
  });

  // ---- after HTMX swaps ----
  document.body.addEventListener('htmx:afterSwap', (event) => {
    const { id } = event.target;
    if (id === 'ticket-body' || id === 'research-body') {
      const dialog = $(id === 'ticket-body' ? '#ticket-dialog' : '#research-dialog');
      if (!dialog.open) dialog.showModal();
      if (refocusQty) { $('#ticket-qty')?.focus(); refocusQty = false; }
      return;
    }
    if (id === 'desk' || id === 'detail') {
      refreshAll();
      if (id === 'desk') { closeDetail(); syncDisclosures(); }
      // a stock chosen from the list: on a phone, push its screen (a Re-analyse inside the open pane keeps it open)
      if (id === 'detail' && event.detail.requestConfig?.elt?.closest('li[id^="row-"]')) openDetail();
      const what = id === 'detail' ? $('#sum-h')?.textContent.trim() : `the ${$('[aria-current="page"]')?.textContent.trim().split(' ')[0]} tab`;
      $('#desk-status').textContent = `Showing ${what}`;
    }
  });
  document.body.addEventListener('htmx:historyRestore', () => { setBackgroundInert(!!deskRoot()?.hasAttribute('data-detail-open')); refreshAll(); });

  syncDisclosures();
  refreshAll();
})();
