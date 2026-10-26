// Order desk interactivity: signal filters/sort/search, the ticket dialog, and re-sync after HTMX swaps.
// Filtering is done in the browser on server-rendered rows; nothing here ever builds an order.
(() => {
  const state = { tone: 'all', pillar: 'all', query: '', sort: 'order' };
  const SORTS = {
    order: (el) => Number(el.dataset.order),
    impact: (el) => -Math.abs(Number(el.dataset.impact)),
    weight: (el) => -Number(el.dataset.weight),
  };
  const $ = (selector) => document.querySelector(selector);

  function applySignals() {
    const list = $('#signal-list');
    if (!list) return;
    const rows = [...list.querySelectorAll('details')];
    let shown = 0;
    rows.forEach((row) => {
      const visible = (state.tone === 'all' || row.dataset.tone === state.tone)
        && (state.pillar === 'all' || row.dataset.pillar === state.pillar)
        && row.dataset.name.includes(state.query);
      row.hidden = !visible;
      shown += visible;
    });
    rows.sort((a, b) => SORTS[state.sort](a) - SORTS[state.sort](b)).forEach((row) => list.appendChild(row));
    $('#sig-count').textContent = `Showing ${shown} of ${rows.length} signals`;
    document.querySelectorAll('[data-filter]').forEach((button) =>
      button.setAttribute('aria-pressed', String(state[button.dataset.filter] === button.dataset.value)));
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-filter]');
    if (!button) return;
    state[button.dataset.filter] = button.dataset.value;
    applySignals();
  });
  document.addEventListener('input', (event) => {
    if (event.target.id !== 'sig-search') return;
    state.query = event.target.value.trim().toLowerCase();
    applySignals();
  });
  document.addEventListener('change', (event) => {
    if (event.target.id === 'sig-sort') { state.sort = event.target.value; applySignals(); }
    if (event.target.id === 'ticket-qty') state.refocusQty = true;   // the ticket re-renders: put the cursor back afterwards
  });

  document.body.addEventListener('htmx:afterSwap', (event) => {
    const id = event.target.id;
    if (id === 'desk-panel') {
      applySignals();
      $('#sizer')?.dispatchEvent(new Event('input'));   // suggested quantities for the new stock
      $('#desk-status').textContent = `Showing ${$('#sum-h')?.textContent.trim() ?? 'stock'}`;
    }
    if (id === 'ticket-body') {
      const dialog = $('#ticket-dialog');
      if (!dialog.open) dialog.showModal();
      if (state.refocusQty) { $('#ticket-qty')?.focus(); state.refocusQty = false; }
    }
  });

  applySignals();
})();
