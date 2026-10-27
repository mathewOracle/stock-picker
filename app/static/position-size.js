// Position sizing for any element with data-entry / data-stop (intraday setup cards, the swing trade plan).

// Pure function (unit-testable with node): shares to buy so a stop-out loses capital x risk%.
function positionSize(capital, riskPct, entry, stop) {
  const perShare = Math.abs(entry - stop);
  const riskQty = perShare > 0 ? Math.floor((capital * riskPct) / 100 / perShare) : 0;
  const affordable = entry > 0 ? Math.floor(capital / entry) : 0;  // no leverage assumed
  const qty = Math.min(riskQty, affordable);
  return { qty, riskQty, capped: riskQty > affordable, moneyAtRisk: Math.round(qty * perShare) };
}

if (typeof document !== 'undefined') {
  const form = document.getElementById('sizer');
  if (form) {
    const update = () => {
      const capital = Number(form.capital.value) || 0;
      // the input's max is the server's cap (desk.MAX_RISK_PCT): typing more must not show a bigger size than an order would get
      const riskPct = Math.min(Number(form.risk.value) || 0, Number(form.risk.max) || Infinity);
      document.querySelectorAll('[data-entry][data-stop]').forEach((card) => {
        const out = card.querySelector('[data-qty]');
        if (!out) return;
        const size = positionSize(capital, riskPct, Number(card.dataset.entry), Number(card.dataset.stop));
        // say *why* the number is what it is: silent caps look like bugs
        out.textContent = size.capped
          ? `${size.qty} (capital-capped; risk allows ${size.riskQty})`
          : `${size.qty} (risk ${form.dataset.currency || ''}${size.moneyAtRisk.toLocaleString(form.dataset.locale || undefined)})`;
      });
    };
    form.addEventListener('input', update);
    update();
  }
}

if (typeof module !== 'undefined') module.exports = { positionSize };
