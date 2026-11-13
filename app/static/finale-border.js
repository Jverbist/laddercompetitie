(() => {
  const border = document.getElementById("finale-border");
  if (!border) return;

  const start = Date.parse(border.dataset.start);
  const end = Date.parse(border.dataset.end);
  const serverTime = Date.parse(border.dataset.serverTime);
  if (![start, end, serverTime].every(Number.isFinite)) return;

  const offset = serverTime - Date.now();
  let timer;
  const update = () => {
    clearTimeout(timer);
    const now = Date.now() + offset;
    border.hidden = now < start || now >= end;
    const next = now < start ? start : now < end ? end : null;
    if (next !== null) timer = setTimeout(update, Math.min(next - now, 2147483647));
  };
  document.addEventListener("visibilitychange", update);
  update();
})();
