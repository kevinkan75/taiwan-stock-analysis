'use strict';
(() => {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const sections = [...document.querySelectorAll('[role="tabpanel"]')];
  const figures = [...document.querySelectorAll('[data-series]')];
  const indicator = document.getElementById('indicator');
  const toggle = document.getElementById('view-toggle');
  const charts = document.getElementById('charts');
  const table = document.getElementById('annual-table');
  let selected = 0;
  let tableView = false;
  function activate(index, focus = false) {
    selected = index;
    tabs.forEach((tab, i) => {
      tab.setAttribute('aria-selected', String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
      sections[i].hidden = i !== index;
    });
    if (focus) tabs[index].focus();
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => activate(i));
    tab.addEventListener('keydown', event => {
      const next = {ArrowRight:(i+1)%4, ArrowLeft:(i+3)%4, Home:0, End:3}[event.key];
      if (next !== undefined) { event.preventDefault(); activate(next, true); }
    });
  });
  function showData() {
    figures.forEach(figure => { figure.hidden = figure.dataset.series !== indicator.value; });
    charts.hidden = tableView;
    table.hidden = !tableView;
    toggle.setAttribute('aria-pressed', String(tableView));
    toggle.textContent = tableView ? '顯示圖表' : '顯示資料表';
  }
  indicator.addEventListener('change', showData);
  toggle.addEventListener('click', () => { tableView = !tableView; showData(); });
  document.getElementById('print').addEventListener('click', () => window.print());
  let closedDetails = [];
  window.addEventListener('beforeprint', () => {
    closedDetails = [...document.querySelectorAll('details:not([open])')];
    closedDetails.forEach(detail => { detail.open = true; });
  });
  window.addEventListener('afterprint', () => {
    closedDetails.forEach(detail => { detail.open = false; });
    activate(selected); showData();
  });
  activate(0); showData();
})();
