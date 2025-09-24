const tableBody = document.getElementById('table-body');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const pageIndicator = document.getElementById('page-indicator');
const pageSizeSelect = document.getElementById('page-size-select');
const lastUpdated = document.getElementById('last-updated');

const numberFormatter = new Intl.NumberFormat('en-US');
const percentFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

let currentPage = 1;
let pageSize = window.PAGE_SIZE_DEFAULT || 100;
let hasNext = false;
let hasPrevious = false;

const PAGE_SIZE_OPTIONS = [50, 100, 150, 200];

function initPageSizeSelect() {
  pageSizeSelect.innerHTML = '';
  const options = Array.from(new Set([...PAGE_SIZE_OPTIONS, pageSize])).sort((a, b) => a - b);
  options.forEach((option) => {
    const optionEl = document.createElement('option');
    optionEl.value = option;
    optionEl.textContent = option;
    if (option === pageSize) {
      optionEl.selected = true;
    }
    pageSizeSelect.appendChild(optionEl);
  });
}

async function fetchData() {
  pageIndicator.textContent = 'Loading...';
  tableBody.innerHTML = '';

  try {
    const response = await fetch(`/api/volume-changes?page=${currentPage}&page_size=${pageSize}`);
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    const data = await response.json();
    renderTable(data.items);
    updatePagination(data);
    updateLastUpdated(data.items);
  } catch (error) {
    pageIndicator.textContent = 'Error loading data';
    console.error(error);
  }
}

function renderTable(items) {
  if (!items.length) {
    tableBody.innerHTML = '<tr><td colspan="7">No data available</td></tr>';
    return;
  }

  const frag = document.createDocumentFragment();

  items.forEach((item) => {
    const row = document.createElement('tr');
    if (item.is_spike) {
      row.classList.add('spike');
    }

    row.innerHTML = `
      <td>${item.ticker}</td>
      <td>${formatDate(item.last_trade_date)}</td>
      <td>${formatDate(item.previous_trade_date)}</td>
      <td class="numeric">${formatVolume(item.latest_volume)}</td>
      <td class="numeric">${formatVolume(item.previous_volume)}</td>
      <td class="numeric">${formatPercent(item.volume_change_pct)}</td>
      <td class="numeric">${formatRatio(item.volume_ratio)}</td>
    `;

    frag.appendChild(row);
  });

  tableBody.innerHTML = '';
  tableBody.appendChild(frag);
}

function formatDate(value) {
  if (!value) return 'N/A';
  return value;
}

function formatVolume(value) {
  if (value === null || value === undefined) return 'N/A';
  return numberFormatter.format(value);
}

function formatPercent(value) {
  if (value === null || value === undefined) return 'N/A';
  const sign = value > 0 ? '+' : '';
  return `${sign}${percentFormatter.format(value)}%`;
}

function formatRatio(value) {
  if (value === null || value === undefined) return 'N/A';
  return `${percentFormatter.format(value)}x`;
}

function updatePagination(data) {
  hasNext = data.has_next;
  hasPrevious = data.has_previous;

  prevBtn.disabled = !hasPrevious;
  nextBtn.disabled = !hasNext;

  const totalPages = data.total ? Math.ceil(data.total / data.page_size) : 'N/A';
  pageIndicator.textContent = `Page ${data.page} of ${totalPages}`;
}

function updateLastUpdated(items) {
  if (!items.length) {
    lastUpdated.textContent = '';
    return;
  }

  const sample = items[0];
  const kst = new Date(sample.fetched_at_kst);
  const utc = new Date(sample.fetched_at_utc);
  lastUpdated.textContent = `Batch fetched at ${kst.toLocaleString('en-US', { timeZone: 'Asia/Seoul' })} (KST) / ${utc.toUTCString()}`;
}

prevBtn.addEventListener('click', () => {
  if (!hasPrevious) return;
  currentPage -= 1;
  fetchData();
});

nextBtn.addEventListener('click', () => {
  if (!hasNext) return;
  currentPage += 1;
  fetchData();
});

pageSizeSelect.addEventListener('change', (event) => {
  const value = Number(event.target.value);
  if (!Number.isNaN(value)) {
    pageSize = value;
    currentPage = 1;
    fetchData();
  }
});

initPageSizeSelect();
fetchData();
