/**
 * Production Planning Dashboard Frontend Controller
 * Implements all 6 interactive cards from the reference screenshot.
 * Integrates bidirectional interactivity between Card 1 (Production Trend)
 * and Card 4 (Active Issues & Mitigation).
 */

let dashboardData = null;
let masterActivities = [];
let masterIssues = [];
let activeScenarioKey = null;
let trendChart = null;
let offloadingChart = null;
let popupChart = null;
let activePopupChartType = null;
let activeHighlightIssue = null;
let currentView = 'field'; // 'field' (placeholder / Excel upload) or 'terminal' (ETL terminal CSV)

/** Display name for the "no filter" sentinel and the entity column in the current view. */
function entityNoun() {
  return currentView === 'terminal' ? 'Terminal' : 'Field';
}

function displayEntity(name) {
  if (name === 'All Fields') return currentView === 'terminal' ? 'All Terminals' : 'All Fields';
  return name;
}

function applyViewLabels() {
  document.querySelectorAll('.entity-label').forEach(el => { el.textContent = entityNoun(); });
}

// Sort state for tables
let card3SortCol = 'date';
let card3SortAsc = true;
let card4SortCol = 'recovery';
let card4SortAsc = true;
let modalActSortCol = 'date';
let modalActSortAsc = true;
let modalIssSortCol = 'recovery';
let modalIssSortAsc = true;

/**
 * Format impact value ensuring at least 3 decimal places (e.g. -1.5 -> -1.500 kbopd)
 */
function formatImpact(val) {
  if (val === null || val === undefined || val === '' || val === '-') return '-';
  const str = String(val).trim();
  const match = str.match(/([+-]?\d+(?:\.\d+)?)/);
  if (!match) return str;
  const numStr = match[1];
  const num = parseFloat(numStr);
  if (isNaN(num)) return str;

  const parts = numStr.split('.');
  let formattedNum;
  if (parts.length === 1 || parts[1].length < 3) {
    formattedNum = num.toFixed(3);
  } else {
    formattedNum = numStr;
  }

  const unitMatch = str.match(/[a-zA-Z]+/);
  const unit = unitMatch ? unitMatch[0] : 'kbopd';
  return `${formattedNum} ${unit}`;
}

/**
 * Robust date parser for chronological sorting across Card 3 & Card 4
 * Handles: "22 Sep 2026", "24-26 Sep 2026", "2-4 Oct 2026", "20 Sep", "12 Sep"
 * Returns timestamp number in ms for accurate numeric comparison.
 */
function parseDateToSortValue(dateStr) {
  if (!dateStr || dateStr === '-' || dateStr === '—') return 9999999999999;
  const str = String(dateStr).trim();

  const months = {
    jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
    jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11
  };

  // Match day or start of range (e.g. "24-26" -> 24), month, and optional year
  const match = str.match(/(\d{1,2})(?:\s*-\s*\d{1,2})?\s+([A-Za-z]{3})(?:\s+(\d{4}))?/i);
  if (match) {
    const day = parseInt(match[1], 10);
    const mStr = match[2].toLowerCase();
    const month = months[mStr] !== undefined ? months[mStr] : 8;
    const year = match[3] ? parseInt(match[3], 10) : 2026;
    return new Date(year, month, day).getTime();
  }

  // Fallback to Date.parse
  const parsed = Date.parse(str);
  if (!isNaN(parsed)) return parsed;

  const numMatch = str.match(/\d+/);
  if (numMatch) return parseInt(numMatch[0], 10);

  return 9999999999999;
}

/**
 * Resolves the primary date associated with an issue for chronological sorting
 */
function getIssueSortDate(iss) {
  if (!iss) return '-';
  if (iss.recovery && iss.recovery !== '-' && iss.recovery !== '—') return iss.recovery;
  if (iss.date && iss.date !== '-' && iss.date !== '—') return iss.date;
  const text = `${iss.remarks || ''} ${iss.description || ''}`;
  const m = text.match(/\b(\d{1,2}\s+[A-Za-z]{3}(?:\s+\d{4})?)\b/i);
  if (m) return m[1];
  return '-';
}

document.addEventListener('DOMContentLoaded', () => {
  initSidebarToggle();
  initCharts();
  fetchDashboardData();
  setupFilterHandlers();
});

function initSidebarToggle() {
  const btn = document.getElementById('sidebar-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (!btn || !sidebar) return;

  const sync = () => {
    const collapsed = document.documentElement.classList.contains('sidebar-collapsed');
    const label = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    btn.setAttribute('aria-expanded', String(!collapsed));
    btn.setAttribute('aria-label', label);
    btn.title = label;
  };
  sync();

  btn.addEventListener('click', () => {
    const collapsed = document.documentElement.classList.toggle('sidebar-collapsed');
    try {
      localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
    } catch (e) {}
    sync();
  });

  // Charts size to their container, so re-fit them once the width animation ends
  sidebar.addEventListener('transitionend', (e) => {
    if (e.propertyName === 'width') window.dispatchEvent(new Event('resize'));
  });
}

function initCharts() {
  const trendDom = document.getElementById('trendChart');
  const offloadingDom = document.getElementById('offloadingChart');

  if (trendDom) trendChart = echarts.init(trendDom);
  if (offloadingDom) offloadingChart = echarts.init(offloadingDom);

  window.addEventListener('resize', () => {
    if (trendChart) trendChart.resize();
    if (offloadingChart) offloadingChart.resize();
    if (popupChart) popupChart.resize();
  });
}

function setupFilterHandlers() {
  const btnApply = document.getElementById('btn-apply-filters');
  if (btnApply) {
    btnApply.addEventListener('click', applyFilters);
  }

  const uploadInput = document.getElementById('excel-file-input');
  if (uploadInput) {
    uploadInput.addEventListener('change', handleExcelUpload);
  }

  const fieldSelect = document.getElementById('filter-field');
  if (fieldSelect) {
    fieldSelect.addEventListener('change', () => {
      fetchDashboardData(fieldSelect.value);
    });
  }

  const viewSelect = document.getElementById('filter-view');
  if (viewSelect) {
    viewSelect.addEventListener('change', () => setView(viewSelect.value));
  }

  // View All buttons (Cards 3 & 4)
  document.getElementById('btn-view-all-activities')?.addEventListener('click', openActivitiesModal);
  document.getElementById('btn-view-all-issues')?.addEventListener('click', openIssuesModal);

  // Close modals
  document.getElementById('btn-close-activities-modal')?.addEventListener('click', closeActivitiesModal);
  document.getElementById('btn-footer-close-activities')?.addEventListener('click', closeActivitiesModal);
  document.getElementById('modal-activities')?.addEventListener('click', (e) => {
    if (e.target.id === 'modal-activities') closeActivitiesModal();
  });

  document.getElementById('btn-close-issues-modal')?.addEventListener('click', closeIssuesModal);
  document.getElementById('btn-footer-close-issues')?.addEventListener('click', closeIssuesModal);
  document.getElementById('modal-issues')?.addEventListener('click', (e) => {
    if (e.target.id === 'modal-issues') closeIssuesModal();
  });

  // Chart Popup & Deep Zoom Controls
  document.getElementById('btn-expand-trend')?.addEventListener('click', () => openChartPopup('trend'));
  document.getElementById('btn-expand-offloading')?.addEventListener('click', () => openChartPopup('offloading'));
  document.getElementById('btn-chart-zoom-in')?.addEventListener('click', zoomInChart);
  document.getElementById('btn-chart-zoom-out')?.addEventListener('click', zoomOutChart);
  document.getElementById('btn-chart-reset-zoom')?.addEventListener('click', resetZoomChart);
  document.getElementById('btn-chart-export-png')?.addEventListener('click', exportChartPng);
  document.getElementById('btn-close-chart-modal')?.addEventListener('click', closeChartPopup);
  document.getElementById('btn-footer-close-chart')?.addEventListener('click', closeChartPopup);
  document.getElementById('modal-chart-popup')?.addEventListener('click', (e) => {
    if (e.target.id === 'modal-chart-popup') closeChartPopup();
  });

  // Modal filters & search inputs
  document.getElementById('modal-activities-search')?.addEventListener('input', filterAndRenderModalActivities);
  document.getElementById('modal-activities-field-filter')?.addEventListener('change', filterAndRenderModalActivities);
  document.getElementById('modal-activities-status-filter')?.addEventListener('change', filterAndRenderModalActivities);
  document.getElementById('btn-clear-activities-filters')?.addEventListener('click', () => {
    const s = document.getElementById('modal-activities-search');
    const f = document.getElementById('modal-activities-field-filter');
    const st = document.getElementById('modal-activities-status-filter');
    if (s) s.value = '';
    if (f) f.value = 'All Fields';
    if (st) st.value = 'All';
    filterAndRenderModalActivities();
  });

  document.getElementById('modal-issues-search')?.addEventListener('input', filterAndRenderModalIssues);
  document.getElementById('modal-issues-field-filter')?.addEventListener('change', filterAndRenderModalIssues);
  document.getElementById('modal-issues-status-filter')?.addEventListener('change', filterAndRenderModalIssues);
  document.getElementById('btn-clear-issues-filters')?.addEventListener('click', () => {
    const s = document.getElementById('modal-issues-search');
    const f = document.getElementById('modal-issues-field-filter');
    const st = document.getElementById('modal-issues-status-filter');
    if (s) s.value = '';
    if (f) f.value = 'All Fields';
    if (st) st.value = 'All';
    filterAndRenderModalIssues();
  });

  // Global keydown (Escape to close open modals)
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeActivitiesModal();
      closeIssuesModal();
      closeChartPopup();
    }
  });

  // Interactive Stat Chips (Card 6)
  setupStatChipsInteractivity();

  // Initialize interactive Period popup (Month, Single Date, Date Range)
  initPeriodPicker();
}

async function fetchDashboardData(fieldFilter = 'All Fields') {
  try {
    const res = await fetch(`/api/dashboard?view=${currentView}&field=${encodeURIComponent(fieldFilter)}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${res.status}`);
    }
    dashboardData = await res.json();

    // Cache unconstrained master datasets
    if (fieldFilter === 'All Fields' || masterActivities.length === 0) {
      masterActivities = JSON.parse(JSON.stringify(dashboardData.planned_activities || []));
      masterIssues = JSON.parse(JSON.stringify(dashboardData.active_issues || []));
    }

    renderAllCards(dashboardData);
  } catch (err) {
    console.error('Failed to load dashboard data:', err);
    showToast(`Error loading dashboard: ${err.message}`);
  }
}

function setView(view) {
  currentView = view === 'terminal' ? 'terminal' : 'field';
  const viewSelect = document.getElementById('filter-view');
  if (viewSelect) viewSelect.value = currentView;
  masterActivities = [];
  masterIssues = [];
  activeScenarioKey = null;
  applyViewLabels();
  return fetchDashboardData('All Fields');
}

function updateFieldPicklist(availableFields, selectedField) {
  const select = document.getElementById('filter-field');
  if (!select) return;

  const currentVal = selectedField || select.value || 'All Fields';
  const fields = Array.isArray(availableFields) && availableFields.length
    ? availableFields
    : ['Field A', 'Field B', 'Field C', 'Field D'];

  // Check if dropdown already has these options
  const existingOptions = Array.from(select.options).map(o => o.value);
  const allLabel = displayEntity('All Fields');
  const optionsMatch = existingOptions.length === (fields.length + 1) &&
    existingOptions[0] === 'All Fields' &&
    select.options[0].textContent === allLabel &&
    fields.every((f, i) => existingOptions[i + 1] === f);

  if (!optionsMatch) {
    select.innerHTML = `<option value="All Fields">${allLabel}</option>`;
    fields.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f;
      opt.textContent = f;
      select.appendChild(opt);
    });
  }

  // Set selected value
  if (Array.from(select.options).some(o => o.value === currentVal)) {
    select.value = currentVal;
  } else {
    select.value = 'All Fields';
  }
}

function renderAllCards(data) {
  // Metadata update
  const lastUpdatedEl = document.getElementById('last-updated-val');
  if (lastUpdatedEl) lastUpdatedEl.innerText = data.metadata.last_updated;

  // Dynamic field picklist and header badge
  const selectedField = data.metadata.selected_field || 'All Fields';
  updateFieldPicklist(data.metadata.available_fields, selectedField);

  const trendBadge = document.getElementById('trend-field-badge');
  if (trendBadge) {
    trendBadge.innerText = displayEntity(selectedField);
  }

  // Period label follows the data being shown (terminal CSV and field data cover different months)
  const periodText = document.getElementById('period-display-text');
  const periodInput = document.getElementById('filter-period');
  if (data.metadata.period && periodText && periodInput) {
    periodText.innerText = data.metadata.period;
    periodInput.value = data.metadata.period;
  }

  const offloadSubtitle = document.getElementById('offloading-subtitle');
  if (offloadSubtitle) {
    offloadSubtitle.innerText = data.offloading_planning?.estimate_note
      || 'Track inventory and forecast next tanker offloading date.';
  }

  // 1. Production Trend (Card 1)
  renderCard1ProductionTrend(data.production_trend, data.active_issues, selectedField, data.planned_activities);

  // 2. Field Performance (Card 2)
  renderCard2FieldPerformance(data.field_performance, selectedField);

  // 3. Planned Activities (Card 3)
  renderCard3PlannedActivities(data.planned_activities);

  // 4. Active Issues & Mitigation (Card 4)
  renderCard4ActiveIssues(data.active_issues);

  // 5. Offloading Planning (Card 5)
  renderCard5OffloadingPlanning(data.offloading_planning);

  // 6. Offloading Estimation (Card 6)
  renderCard6OffloadingEstimation(data.offloading_estimation);

  // Footer AI Insight
  const aiText = document.getElementById('ai-insight-text');
  if (aiText && data.ai_insight) {
    aiText.innerText = data.ai_insight.text;
  }
}

// -------------------------------------------------------------
// -------------------------------------------------------------
// Helper to extract clean day and month (e.g. "18 sep" from "18 Sep 2026", "18 Sep", or "2026-09-18")
function cleanTrendDate(str) {
  if (!str) return '';
  const m = String(str).match(/(\d{1,2}\s+[A-Za-z]{3})/);
  return m ? m[1].toLowerCase() : String(str).trim().toLowerCase();
}

// Robust date context resolver: links dates to Card 4 issues, events, and planned activities
function getTrendContextForDate(date, events = [], activeIssues = [], selectedField = 'All Fields', plannedActivities = []) {
  if (!date) return { matchedEvent: null, matchedIssues: [], matchedActivities: [] };
  const cDate = cleanTrendDate(date);
  const dayMatch = String(date).match(/\d+/);
  const dayNum = dayMatch ? parseInt(dayMatch[0], 10) : 0;

  // 1. Matched event from production trend events
  const matchedEvent = (events || []).find(e => {
    const eStart = cleanTrendDate(e.date);
    const eEnd = cleanTrendDate(e.endDate);
    if (eStart === cDate || eEnd === cDate) return true;
    if (eStart && eEnd && String(e.date).toLowerCase().includes('sep') && String(date).toLowerCase().includes('sep')) {
      const sNum = parseInt((eStart.match(/\d+/) || [0])[0], 10);
      const endNum = parseInt((eEnd.match(/\d+/) || [0])[0], 10);
      if (dayNum >= sNum && dayNum <= endNum) return true;
    }
    return false;
  });

  // 2. Matched issues from Card 4 (Active Issues & Mitigation)
  const matchedIssues = (activeIssues || []).filter(iss => {
    if (selectedField !== 'All Fields' && iss.field && iss.field !== selectedField) {
      return false;
    }

    // Match explicit date or recovery date
    if (iss.recovery && cleanTrendDate(iss.recovery) === cDate) return true;
    if (iss.date && cleanTrendDate(iss.date) === cDate) return true;

    // Match date mentioned anywhere in remarks or description (e.g. "on 18 Sep")
    const desc = (iss.description || iss.remarks || '').toLowerCase();
    if (cDate && desc.includes(cDate)) return true;

    // Match linked event title with issue title or keywords
    if (matchedEvent) {
      const evTitle = (matchedEvent.title || '').toLowerCase();
      const issTitle = (iss.issue || '').toLowerCase();
      if (evTitle.includes(issTitle) || issTitle.includes(evTitle)) return true;
      const keywords = ['compressor', 'separator', 'pump', 'gas lift', 'shutdown', 'trip', 'valve', 'transmitter'];
      for (const kw of keywords) {
        if (evTitle.includes(kw) && issTitle.includes(kw)) return true;
      }
    }

    return false;
  });

  // 3. Matched planned activities from Card 3
  const matchedActivities = (plannedActivities || []).filter(act => {
    if (selectedField !== 'All Fields' && act.field && act.field !== selectedField) {
      return false;
    }
    const actDate = cleanTrendDate(act.date);
    if (actDate === cDate) return true;
    if (act.date && act.date.includes('-')) {
      const parts = act.date.split('-');
      const sNum = parseInt((parts[0].match(/\d+/) || [0])[0], 10);
      const endNum = parseInt((parts[1].match(/\d+/) || [0])[0], 10);
      if (dayNum >= sNum && dayNum <= endNum) return true;
    }
    return false;
  });

  return { matchedEvent, matchedIssues, matchedActivities };
}

// Builds the production trend ECharts option with full remarks tooltip support
function buildCard1ProductionTrendOption(pt, activeIssues = [], selectedField = 'All Fields', plannedActivities = [], isPopup = false) {
  if (!pt) return null;

  const dates = pt.dates || [];
  const planData = pt.plan || [];
  const actualData = pt.actual || [];
  const forecastData = pt.forecast || [];
  const events = pt.events || [];

  // Dynamically compute yMax to fit data cleanly
  const allNums = [
    ...planData,
    ...actualData,
    ...forecastData
  ].filter(v => v !== null && v !== undefined && !isNaN(v) && typeof v === 'number');

  const maxVal = allNums.length ? Math.max(...allNums) : 50;
  const yMax = Math.max(10, Math.ceil((maxVal * 1.15) / 5) * 5);

  // Map Actual series points: distinct accent dot on dates with active issues or events
  const actualSeriesData = dates.map((date, dIdx) => {
    const val = actualData[dIdx];
    if (val === null || val === undefined) return null;

    const ctx = getTrendContextForDate(date, events, activeIssues, selectedField, plannedActivities);
    const hasIssue = ctx.matchedIssues.length > 0 || (ctx.matchedEvent && ctx.matchedEvent.type === 'issue');
    const hasActivity = ctx.matchedActivities.length > 0 || (ctx.matchedEvent && ctx.matchedEvent.type === 'activity');

    if (hasIssue || hasActivity) {
      return {
        value: val,
        symbol: 'circle',
        symbolSize: isPopup ? 11 : 10,
        cursor: 'pointer',
        itemStyle: {
          color: hasIssue ? '#EF4444' : '#0284C7',
          borderColor: '#FFFFFF',
          borderWidth: 2.5,
          shadowBlur: 5,
          shadowColor: 'rgba(0, 0, 0, 0.3)'
        },
        emphasis: {
          scale: 1.6,
          itemStyle: {
            borderColor: '#FFFFFF',
            borderWidth: 3.5,
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.45)'
          }
        },
        eventMeta: ctx.matchedIssues[0] || ctx.matchedEvent || ctx.matchedActivities[0]
      };
    }

    return {
      value: val,
      symbol: 'circle',
      symbolSize: isPopup ? 8 : 7,
      cursor: 'pointer',
      itemStyle: { color: '#0D9488' },
      emphasis: {
        scale: 1.6,
        itemStyle: {
          borderColor: '#FFFFFF',
          borderWidth: 2.5,
          shadowBlur: 7,
          shadowColor: 'rgba(0, 0, 0, 0.3)'
        }
      }
    };
  });

  const option = {
    backgroundColor: '#FFFFFF',
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(15, 23, 42, 0.96)',
      borderColor: '#334155',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#F8FAFC', fontSize: 12, lineHeight: 18 },
      extraCssText: 'border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.35); pointer-events: none; width: max-content; min-width: 260px; max-width: 380px; white-space: normal !important; word-break: break-word !important; overflow-wrap: break-word !important; box-sizing: border-box; z-index: 100005;',
      position: function (pos, params, el, elRect, size) {
        if (!size || !size.contentSize || !size.viewSize) return [pos[0] + 12, Math.max(10, pos[1] - 40)];
        const fitsAbove = pos[1] - size.contentSize[1] - 14 >= 10;
        const top = fitsAbove ? pos[1] - size.contentSize[1] - 14 : Math.min(pos[1] + 18, size.viewSize[1] - size.contentSize[1] - 10);
        const left = Math.min(Math.max(10, pos[0] - size.contentSize[0] / 2), size.viewSize[0] - size.contentSize[0] - 10);
        return [Math.max(10, left), Math.max(10, top)];
      },
      formatter: function (params) {
        const p = Array.isArray(params) ? params[0] : params;
        const date = p.name || (p.dataIndex != null ? dates[p.dataIndex] : (p.axisValue || ''));
        const dIdx = dates.indexOf(date) >= 0 ? dates.indexOf(date) : (p.dataIndex != null ? p.dataIndex : -1);
        const plan = (dIdx >= 0 && planData[dIdx] != null) ? `${planData[dIdx]} ${pt.unit || 'kbopd'}` : 'N/A';
        const act = (dIdx >= 0 && actualData[dIdx] != null) ? `${actualData[dIdx]} ${pt.unit || 'kbopd'}` : null;
        const fc = (dIdx >= 0 && forecastData[dIdx] != null) ? `${forecastData[dIdx]} ${pt.unit || 'kbopd'}` : null;

        const ctx = getTrendContextForDate(date, events, activeIssues, selectedField, plannedActivities);
        let itemsHtml = '';

        // Render matched issues from Card 4 (Active Issues & Mitigation)
        if (ctx.matchedIssues.length > 0) {
          ctx.matchedIssues.forEach(iss => {
            const isClosed = iss.status === 'Closed';
            const badgeBg = isClosed ? '#10B981' : (iss.status === 'In Progress' ? '#F59E0B' : '#EF4444');
            const remarksText = iss.remarks || iss.description || 'Standard operational mitigation active.';

            itemsHtml += `
              <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #334155;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                  <span style="background: ${badgeBg}; color: #FFFFFF; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; display: inline-block;">
                    ${iss.issue}
                  </span>
                  <span style="font-size: 11px; font-weight: 700; color: #F87171;">
                    ${formatImpact(iss.impact)}
                  </span>
                </div>
                <div style="font-size: 11px; color: #CBD5E1; line-height: 15px;">
                  Field: <strong>${iss.field || 'All'}</strong> &bull; Status: <strong style="color: #FBBF24;">${iss.status}</strong>
                  ${iss.recovery && iss.recovery !== '-' ? ` &bull; Recovery: <strong>${iss.recovery}</strong>` : ''}
                </div>
                <div style="background: rgba(30, 41, 59, 0.85); border-left: 3px solid ${badgeBg}; border-radius: 4px; padding: 7px 10px; margin-top: 6px; white-space: normal !important; word-wrap: break-word !important; overflow-wrap: break-word !important; box-sizing: border-box;">
                  <span style="color: #94A3B8; font-size: 9px; font-weight: 700; display: block; text-transform: uppercase; margin-bottom: 3px; letter-spacing: 0.5px;">Remarks (Card 4):</span>
                  <div style="color: #F8FAFC; font-size: 11px; line-height: 16px; margin: 0; padding: 0; white-space: normal !important; word-wrap: break-word !important; overflow-wrap: break-word !important; word-break: normal;">${remarksText}</div>
                </div>
              </div>
            `;
          });
        } else if (ctx.matchedEvent) {
          // If no specific Card 4 issue matched, render from matchedEvent
          const ev = ctx.matchedEvent;
          const isIssue = ev.type === 'issue' ||
            ev.title.toLowerCase().includes('trip') ||
            ev.title.toLowerCase().includes('shutdown');
          const badgeBg = isIssue ? '#EF4444' : '#0284C7';
          const impactColor = isIssue ? '#F87171' : '#38BDF8';
          const remarksText = ev.description || ev.remarks || 'Standard operational highlight.';

          itemsHtml += `
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #334155;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="background: ${badgeBg}; color: #FFFFFF; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; display: inline-block;">
                  ${ev.title}
                </span>
                <span style="font-size: 11px; font-weight: 700; color: ${impactColor};">
                  ${formatImpact(ev.impact)}
                </span>
              </div>
              <div style="font-size: 11px; color: #CBD5E1; line-height: 15px;">
                Field: <strong>${ev.field || 'All'}</strong>
                ${ev.status ? ` &bull; Status: <strong style="color: #FBBF24;">${ev.status}</strong>` : ''}
                ${ev.recovery ? ` &bull; Recovery: <strong>${ev.recovery}</strong>` : ''}
              </div>
              <div style="background: rgba(30, 41, 59, 0.85); border-left: 3px solid ${badgeBg}; border-radius: 4px; padding: 7px 10px; margin-top: 6px; white-space: normal !important; word-wrap: break-word !important; overflow-wrap: break-word !important; box-sizing: border-box;">
                <span style="color: #94A3B8; font-size: 9px; font-weight: 700; display: block; text-transform: uppercase; margin-bottom: 3px; letter-spacing: 0.5px;">Remarks (Card 4):</span>
                <div style="color: #F8FAFC; font-size: 11px; line-height: 16px; margin: 0; padding: 0; white-space: normal !important; word-wrap: break-word !important; overflow-wrap: break-word !important; word-break: normal;">${remarksText}</div>
              </div>
            </div>
          `;
        }

        // Render planned activities from Card 3 if present
        if (ctx.matchedActivities.length > 0 && ctx.matchedIssues.length === 0 && !ctx.matchedEvent) {
          ctx.matchedActivities.forEach(act => {
            itemsHtml += `
              <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #334155;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                  <span style="background: #0284C7; color: #FFFFFF; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; display: inline-block;">
                    ${act.activity}
                  </span>
                  <span style="font-size: 11px; font-weight: 700; color: #38BDF8;">
                    ${formatImpact(act.expected_impact || act.impact)}
                  </span>
                </div>
                <div style="font-size: 11px; color: #CBD5E1; line-height: 15px;">
                  Field: <strong>${act.field || 'All'}</strong> &bull; Status: <strong style="color: #38BDF8;">${act.status}</strong>
                </div>
                <div style="background: rgba(30, 41, 59, 0.85); border-left: 3px solid #0284C7; border-radius: 4px; padding: 7px 10px; margin-top: 6px; white-space: normal !important; word-wrap: break-word !important; overflow-wrap: break-word !important; box-sizing: border-box;">
                  <span style="color: #94A3B8; font-size: 9px; font-weight: 700; display: block; text-transform: uppercase; margin-bottom: 3px; letter-spacing: 0.5px;">Activity Details (Card 3):</span>
                  <div style="color: #F8FAFC; font-size: 11px; line-height: 16px; margin: 0; padding: 0; white-space: normal !important; word-wrap: break-word !important; overflow-wrap: break-word !important; word-break: normal;">${act.activity} scheduled for ${act.date} on ${act.field}.</div>
                </div>
              </div>
            `;
          });
        }

        return `
          <div style="max-width: 350px; width: 100%; white-space: normal !important; word-wrap: break-word !important; overflow-wrap: break-word !important; box-sizing: border-box;">
            <div style="font-weight: 700; font-size: 13px; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #334155; font-family: monospace;">
              ${date} 2026 ${selectedField !== 'All Fields' ? `<span style="color: #38BDF8; font-size: 11px; font-weight: normal;">(${selectedField})</span>` : ''}
              ${p.seriesName ? `<span style="font-size: 10px; color: #94A3B8; font-weight: normal; margin-left: 6px;">[${p.seriesName}]</span>` : ''}
            </div>
            <div style="display: flex; justify-content: space-between; gap: 12px; margin-bottom: 3px;">
              <span style="color: #94A3B8;">Plan:</span>
              <strong>${plan}</strong>
            </div>
            ${act ? `
            <div style="display: flex; justify-content: space-between; gap: 12px; margin-bottom: 3px;">
              <span style="color: #94A3B8;">Actual:</span>
              <strong style="color: #0D9488;">${act}</strong>
            </div>` : ''}
            ${fc ? `
            <div style="display: flex; justify-content: space-between; gap: 12px; margin-bottom: 3px;">
              <span style="color: #94A3B8;">Forecast:</span>
              <strong style="color: #06B6D4;">${fc}</strong>
            </div>` : ''}
            ${itemsHtml}
          </div>
        `;
      }
    },
    legend: {
      data: ['Plan', 'Actual', 'Forecast'],
      bottom: isPopup ? 38 : 6,
      left: 'center',
      itemGap: 28,
      itemWidth: 18,
      itemHeight: 5,
      icon: 'roundRect',
      textStyle: { color: '#64748B', fontSize: 11, fontWeight: 500 }
    },
    grid: isPopup ? {
      left: '4%',
      right: '4%',
      top: '10%',
      bottom: '16%',
      containLabel: true
    } : {
      left: '3%',
      right: '4%',
      top: '12%',
      bottom: '14%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#CBD5E1' } },
      axisLabel: { color: '#64748B', fontSize: 11 },
      axisTick: { alignWithLabel: true }
    },
    yAxis: {
      type: 'value',
      name: `Production (${pt.unit || 'kbopd'})`,
      nameTextStyle: { color: '#64748B', fontSize: 11, padding: [0, 0, 0, 20] },
      min: 0,
      max: yMax,
      splitLine: { lineStyle: { color: '#F1F5F9' } },
      axisLabel: { color: '#64748B', fontSize: 11 }
    },
    series: [
      {
        name: 'Plan',
        type: 'line',
        data: planData,
        lineStyle: {
          color: '#0EA5E9',
          type: 'dashed',
          width: 2
        },
        itemStyle: { color: '#0EA5E9' },
        symbol: 'circle',
        symbolSize: isPopup ? 7 : 6,
        showSymbol: true,
        cursor: 'pointer',
        label: { show: false },
        endLabel: { show: false },
        emphasis: {
          label: { show: false },
          scale: 1.5,
          itemStyle: {
            borderColor: '#FFFFFF',
            borderWidth: 2
          }
        }
      },
      {
        name: 'Actual',
        type: 'line',
        data: actualSeriesData,
        lineStyle: {
          color: '#0D9488',
          width: 2.8
        },
        itemStyle: { color: '#0D9488' },
        symbol: 'circle',
        symbolSize: isPopup ? 8 : 7,
        showSymbol: true,
        cursor: 'pointer',
        label: { show: false },
        endLabel: { show: false },
        emphasis: {
          label: { show: false },
          scale: 1.6
        }
      },
      {
        name: 'Forecast',
        type: 'line',
        data: forecastData,
        lineStyle: {
          color: '#0D9488',
          type: 'dashed',
          width: 2.2
        },
        itemStyle: { color: '#0D9488' },
        symbol: 'circle',
        symbolSize: isPopup ? 7 : 6,
        showSymbol: true,
        cursor: 'pointer',
        label: { show: false },
        endLabel: { show: false },
        emphasis: {
          label: { show: false },
          scale: 1.5,
          itemStyle: {
            borderColor: '#FFFFFF',
            borderWidth: 2
          }
        }
      }
    ]
  };

  if (isPopup) {
    option.dataZoom = [
      {
        type: 'inside',
        start: 0,
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true
      },
      {
        type: 'slider',
        show: true,
        start: 0,
        end: 100,
        bottom: 8,
        height: 28,
        borderColor: '#CBD5E1',
        fillerColor: 'rgba(13, 148, 136, 0.15)',
        handleStyle: {
          color: '#0D9488',
          borderColor: '#0F766E'
        },
        textStyle: { color: '#64748B', fontSize: 11 }
      }
    ];
  }

  return option;
}

// -------------------------------------------------------------
// CARD 1: Production Trend (Clean, Toned-Down Executive Chart)
// Full operational issues & Card 4 Remarks accessible on hover
// -------------------------------------------------------------
function renderCard1ProductionTrend(pt, activeIssues = [], selectedField = 'All Fields', plannedActivities = []) {
  if (!trendChart || !pt) return;

  const option = buildCard1ProductionTrendOption(pt, activeIssues, selectedField, plannedActivities, false);
  if (!option) return;

  trendChart.setOption(option, true);

  // Click handler on chart point: clicking an event point highlights Card 4
  trendChart.off('click');
  trendChart.on('click', function (params) {
    const date = params.name;
    const ctx = getTrendContextForDate(date, pt.events || [], activeIssues, selectedField, plannedActivities);
    if (ctx.matchedIssues.length > 0) {
      highlightLinkedIssue(ctx.matchedIssues[0].issue);
    } else if (ctx.matchedEvent) {
      highlightLinkedIssue(ctx.matchedEvent.title);
    }
  });
}

// -------------------------------------------------------------
// CARD 2: Field Performance
// -------------------------------------------------------------
function renderCard2FieldPerformance(fp, selectedField = 'All Fields') {
  const tbody = document.getElementById('field-performance-tbody');
  if (!tbody || !fp) return;
  tbody.innerHTML = '';

  (fp.rows || []).forEach(r => {
    const tr = document.createElement('tr');
    const isSelected = selectedField && selectedField === r.field;
    tr.className = isSelected ? 'table-row-interactive active-field-row' : 'table-row-interactive';
    tr.onclick = () => {
      const nextField = isSelected ? 'All Fields' : r.field;
      filterByField(nextField);
    };

    const attainmentClass = r.attainment >= 95 ? 'pill-green' : (r.attainment >= 90 ? 'pill-amber' : 'pill-red');
    const varianceClass = r.variance < 0 ? 'variance-negative' : 'variance-positive';
    const varianceStr = r.variance < 0 ? `${r.variance}` : `+${r.variance}`;
    const sparklineSvg = generateSparklineSvg(r.trend, r.variance >= 0 ? '#10B981' : '#EF4444');

    tr.innerHTML = `
      <td style="font-weight: 600;">${r.field}${isSelected ? ' <span style="font-size: 11px; color: #0284C7; font-weight: bold;">&#10003;</span>' : ''}</td>
      <td>${r.plan.toFixed(1)}</td>
      <td>${r.actual.toFixed(1)}</td>
      <td class="${varianceClass}">${varianceStr}</td>
      <td><span class="badge-pill ${attainmentClass}">${r.attainment}%</span></td>
      <td>${sparklineSvg}</td>
    `;
    tbody.appendChild(tr);
  });

  // Total row
  const tot = fp.total;
  if (tot) {
    const totTr = document.createElement('tr');
    totTr.className = 'total-row';
    totTr.style.cursor = 'pointer';
    totTr.title = 'Click to view All Fields';
    totTr.onclick = () => filterByField('All Fields');
    totTr.innerHTML = `
      <td><strong>Total</strong></td>
      <td><strong>${tot.plan.toFixed(1)}</strong></td>
      <td><strong>${tot.actual.toFixed(1)}</strong></td>
      <td class="variance-negative"><strong>${tot.variance}</strong></td>
      <td><span class="badge-pill pill-slate"><strong>${tot.attainment}%</strong></span></td>
      <td>${generateSparklineSvg(tot.trend, '#0284C7')}</td>
    `;
    tbody.appendChild(totTr);
  }
}

function generateSparklineSvg(values, strokeColor) {
  if (!values || values.length < 2) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 60;
  const height = 18;

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  return `
    <svg class="sparkline-svg" viewBox="0 0 ${width} ${height}">
      <polyline fill="none" stroke="${strokeColor}" stroke-width="1.8" stroke-linecap="round" points="${points}" />
    </svg>
  `;
}

// -------------------------------------------------------------
// CARD 3: Planned Activities (Upcoming) - Sorted by Date
// -------------------------------------------------------------
function renderCard3PlannedActivities(activities) {
  const tbody = document.getElementById('planned-activities-tbody');
  if (!tbody || !activities) return;
  tbody.innerHTML = '';
  if (!activities.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #94A3B8; padding: 22px;">No planned activities.</td></tr>';
    return;
  }

  // Sort activities array based on card3SortCol and card3SortAsc
  const sorted = activities.map((item, originalIndex) => ({ item, originalIndex }));
  sorted.sort((a, b) => {
    let valA, valB;
    if (card3SortCol === 'date') {
      valA = parseDateToSortValue(a.item.date);
      valB = parseDateToSortValue(b.item.date);
      return card3SortAsc ? valA - valB : valB - valA;
    } else if (card3SortCol === 'expected_impact' || card3SortCol === 'impact') {
      const numA = parseFloat((String(a.item.expected_impact || a.item.impact || '0').match(/-?\d+(?:\.\d+)?/) || [0])[0]);
      const numB = parseFloat((String(b.item.expected_impact || b.item.impact || '0').match(/-?\d+(?:\.\d+)?/) || [0])[0]);
      return card3SortAsc ? numA - numB : numB - numA;
    } else {
      valA = String(a.item[card3SortCol] || '').toLowerCase();
      valB = String(b.item[card3SortCol] || '').toLowerCase();
      return card3SortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
  });

  // Update table header sort indicator icons
  ['date', 'activity', 'field', 'expected_impact', 'status'].forEach(col => {
    const icon = document.getElementById(`sort-card3-${col}`);
    if (icon) {
      icon.textContent = (card3SortCol === col) ? (card3SortAsc ? '▲' : '▼') : '';
    }
  });

  sorted.forEach(({ item: act, originalIndex: origIdx }) => {
    const tr = document.createElement('tr');

    // Status pill style mapping
    let pillClass = 'pill-blue';
    if (act.status === 'In Progress') pillClass = 'pill-amber';
    else if (act.status === 'Completed') pillClass = 'pill-green';
    else if (act.status === 'Deferred') pillClass = 'pill-slate';
    else if (act.status === 'Unconfirmed') pillClass = 'pill-amber';

    tr.innerHTML = `
      <td style="color: #64748B; font-size: 11px;">${act.date}</td>
      <td style="font-weight: 600;">${act.activity}</td>
      <td>${act.field}</td>
      <td style="color: #EF4444; font-weight: 600;">${formatImpact(act.expected_impact || act.impact)}</td>
      <td>
        <div class="status-dropdown-wrap">
          <button class="status-badge-btn ${pillClass}" onclick="toggleStatusMenu(event, ${origIdx})" title="Click to change status">
            <span>${act.status}</span>
            <span class="status-caret">&#9660;</span>
          </button>
          <div id="status-menu-${origIdx}" class="status-menu-popup">
            <button class="status-menu-item" onclick="setActivityStatus(${origIdx}, 'Planned', 'pill-blue')">
              <span class="status-dot status-dot-blue"></span> Planned
            </button>
            <button class="status-menu-item" onclick="setActivityStatus(${origIdx}, 'In Progress', 'pill-amber')">
              <span class="status-dot status-dot-amber"></span> In Progress
            </button>
            <button class="status-menu-item" onclick="setActivityStatus(${origIdx}, 'Completed', 'pill-green')">
              <span class="status-dot status-dot-green"></span> Completed
            </button>
            <button class="status-menu-item" onclick="setActivityStatus(${origIdx}, 'Deferred', 'pill-slate')">
              <span class="status-dot status-dot-slate"></span> Deferred
            </button>
          </div>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.sortCard3Table = function(col) {
  if (card3SortCol === col) {
    card3SortAsc = !card3SortAsc;
  } else {
    card3SortCol = col;
    card3SortAsc = true;
  }
  if (dashboardData && dashboardData.planned_activities) {
    renderCard3PlannedActivities(dashboardData.planned_activities);
  }
};

function toggleStatusMenu(event, idx) {
  event.stopPropagation();
  // Close any other open status menus first
  document.querySelectorAll('.status-menu-popup').forEach(m => {
    if (m.id !== `status-menu-${idx}`) m.classList.remove('active');
  });
  const menu = document.getElementById(`status-menu-${idx}`);
  if (menu) menu.classList.toggle('active');
}

function setActivityStatus(idx, newStatus, pillClass) {
  const menu = document.getElementById(`status-menu-${idx}`);
  if (menu) menu.classList.remove('active');

  // Update in local dataset
  if (dashboardData && dashboardData.planned_activities && dashboardData.planned_activities[idx]) {
    const item = dashboardData.planned_activities[idx];
    item.status = newStatus;
    const match = masterActivities.find(a => a.activity === item.activity && a.date === item.date);
    if (match) match.status = newStatus;
  }

  // Update DOM button immediately
  if (menu && menu.previousElementSibling) {
    const btn = menu.previousElementSibling;
    btn.className = `status-badge-btn ${pillClass}`;
    const txtSpan = btn.querySelector('span:first-child');
    if (txtSpan) txtSpan.innerText = newStatus;
  }

  // Sync to server runtime
  fetch('/api/activity_status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index: idx, status: newStatus, view: currentView })
  }).then(() => {
    showToast(`Activity status set to ${newStatus}`);
  }).catch(err => console.error('Status sync error:', err));
}

// Global click listener to dismiss open status popups
document.addEventListener('click', function () {
  document.querySelectorAll('.status-menu-popup').forEach(m => m.classList.remove('active'));
});

// -------------------------------------------------------------
// CARD 4: Active Issues & Mitigation (Linked to Card 1, Sorted by Date)
// -------------------------------------------------------------
function renderCard4ActiveIssues(issues) {
  const tbody = document.getElementById('active-issues-tbody');
  if (!tbody || !issues) return;
  tbody.innerHTML = '';
  if (!issues.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #94A3B8; padding: 22px;">No active issues reported.</td></tr>';
    return;
  }

  // Sort issues array based on card4SortCol and card4SortAsc
  const sorted = issues.map((item, originalIndex) => ({ item, originalIndex }));
  sorted.sort((a, b) => {
    let valA, valB;
    if (card4SortCol === 'recovery' || card4SortCol === 'date') {
      valA = parseDateToSortValue(getIssueSortDate(a.item));
      valB = parseDateToSortValue(getIssueSortDate(b.item));
      return card4SortAsc ? valA - valB : valB - valA;
    } else if (card4SortCol === 'impact') {
      const numA = parseFloat((String(a.item.impact || '0').match(/-?\d+(?:\.\d+)?/) || [0])[0]);
      const numB = parseFloat((String(b.item.impact || '0').match(/-?\d+(?:\.\d+)?/) || [0])[0]);
      return card4SortAsc ? numA - numB : numB - numA;
    } else {
      valA = String(a.item[card4SortCol] || '').toLowerCase();
      valB = String(b.item[card4SortCol] || '').toLowerCase();
      return card4SortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
  });

  // Update table header sort indicator icons
  ['issue', 'field', 'impact', 'status', 'recovery'].forEach(col => {
    const icon = document.getElementById(`sort-card4-${col}`);
    if (icon) {
      icon.textContent = (card4SortCol === col) ? (card4SortAsc ? '▲' : '▼') : '';
    }
  });

  sorted.forEach(({ item: iss, originalIndex: origIdx }) => {
    const tr = document.createElement('tr');
    tr.id = `issue-row-${origIdx}`;
    tr.className = 'table-row-interactive';
    
    // Status pill style mapping
    let pillClass = 'pill-red';
    if (iss.status === 'Monitoring') pillClass = 'pill-blue';
    else if (iss.status === 'In Progress') pillClass = 'pill-amber';
    else if (iss.status === 'Closed') pillClass = 'pill-green';
    else if (iss.status === 'Open') pillClass = 'pill-red';

    tr.innerHTML = `
      <td style="font-weight: 600;">${iss.issue}</td>
      <td>${iss.field}</td>
      <td style="color: #EF4444; font-weight: 600;">${formatImpact(iss.impact)}</td>
      <td>
        <div class="status-dropdown-wrap">
          <button class="status-badge-btn ${pillClass}" onclick="toggleIssueStatusMenu(event, ${origIdx})" title="Click to change status">
            <span>${iss.status}</span>
            <span class="status-caret">&#9660;</span>
          </button>
          <div id="issue-status-menu-${origIdx}" class="status-menu-popup">
            <button class="status-menu-item" onclick="setIssueStatus(event, ${origIdx}, 'Open', 'pill-red')">
              <span class="status-dot status-dot-red"></span> Open
            </button>
            <button class="status-menu-item" onclick="setIssueStatus(event, ${origIdx}, 'In Progress', 'pill-amber')">
              <span class="status-dot status-dot-amber"></span> In Progress
            </button>
            <button class="status-menu-item" onclick="setIssueStatus(event, ${origIdx}, 'Monitoring', 'pill-blue')">
              <span class="status-dot status-dot-blue"></span> Monitoring
            </button>
            <button class="status-menu-item" onclick="setIssueStatus(event, ${origIdx}, 'Closed', 'pill-green')">
              <span class="status-dot status-dot-green"></span> Closed
            </button>
          </div>
        </div>
      </td>
      <td style="color: #64748B; font-size: 11px;">${iss.recovery || '—'}</td>
    `;

    // Interactivity: hover/click row highlights event on trend chart
    tr.onmouseenter = () => highlightTrendPinForIssue(iss.issue);
    tr.onmouseleave = () => resetTrendHighlight();
    tr.onclick = (e) => {
      if (e.target.closest('.status-dropdown-wrap')) return;
      showToast(`Selected: ${iss.issue} • ${iss.description || 'Details loaded.'}`);
    };

    tbody.appendChild(tr);
  });
}

window.sortCard4Table = function(col) {
  if (card4SortCol === col) {
    card4SortAsc = !card4SortAsc;
  } else {
    card4SortCol = col;
    card4SortAsc = true;
  }
  if (dashboardData && dashboardData.active_issues) {
    renderCard4ActiveIssues(dashboardData.active_issues);
  }
};

function toggleIssueStatusMenu(event, idx) {
  event.stopPropagation();
  // Close any other open status menus first
  document.querySelectorAll('.status-menu-popup').forEach(m => {
    if (m.id !== `issue-status-menu-${idx}`) m.classList.remove('active');
  });
  const menu = document.getElementById(`issue-status-menu-${idx}`);
  if (menu) menu.classList.toggle('active');
}

function setIssueStatus(event, idx, newStatus, pillClass) {
  if (event) event.stopPropagation();
  const menu = document.getElementById(`issue-status-menu-${idx}`);
  if (menu) menu.classList.remove('active');

  // Update in local dataset
  if (dashboardData && dashboardData.active_issues && dashboardData.active_issues[idx]) {
    const item = dashboardData.active_issues[idx];
    item.status = newStatus;
    const match = masterIssues.find(i => i.issue === item.issue && i.field === item.field);
    if (match) match.status = newStatus;
  }

  // Update DOM button immediately
  if (menu && menu.previousElementSibling) {
    const btn = menu.previousElementSibling;
    btn.className = `status-badge-btn ${pillClass}`;
    const txtSpan = btn.querySelector('span:first-child');
    if (txtSpan) txtSpan.innerText = newStatus;
  }

  // Sync to server runtime
  fetch('/api/issue_status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index: idx, status: newStatus, view: currentView })
  }).then(() => {
    showToast(`Issue status set to ${newStatus}`);
  }).catch(err => console.error('Issue status sync error:', err));
}

function highlightTrendPinForIssue(issueName) {
  if (!trendChart || !dashboardData) return;
  const pt = dashboardData.production_trend;
  if (!pt) return;

  const issues = dashboardData.active_issues || [];
  const targetIssue = issues.find(i => 
    i.issue.toLowerCase().includes(issueName.toLowerCase()) || 
    issueName.toLowerCase().includes(i.issue.toLowerCase())
  );

  let targetDate = null;
  // 1. Try finding in production trend events
  const matchEv = (pt.events || []).find(e => 
    issueName.toLowerCase().includes(e.title.toLowerCase()) || 
    e.title.toLowerCase().includes(issueName.toLowerCase())
  );
  if (matchEv) {
    targetDate = matchEv.date;
  } else if (targetIssue) {
    // 2. Check if recovery date exists in dates
    if (targetIssue.recovery && (pt.dates || []).includes(targetIssue.recovery)) {
      targetDate = targetIssue.recovery;
    } else {
      // 3. Check dates mentioned in description or remarks
      const desc = (targetIssue.description || targetIssue.remarks || '').toLowerCase();
      for (const d of (pt.dates || [])) {
        if (desc.includes(d.toLowerCase())) {
          targetDate = d;
          break;
        }
      }
    }
  }

  if (targetDate) {
    trendChart.dispatchAction({
      type: 'showTip',
      seriesIndex: 1,
      name: targetDate
    });
  }
}

function resetTrendHighlight() {
  if (trendChart) {
    trendChart.dispatchAction({ type: 'hideTip' });
  }
}

function highlightLinkedIssue(eventTitle) {
  const rows = document.querySelectorAll('#active-issues-tbody tr');
  rows.forEach(r => r.classList.remove('highlighted'));

  const issues = dashboardData.active_issues || [];
  const evTitleLower = (eventTitle || '').toLowerCase();
  const evWords = evTitleLower.split(/\s+/).filter(w => w.length > 3);

  issues.forEach((iss, idx) => {
    const issTitleLower = (iss.issue || '').toLowerCase();
    const isMatch = issTitleLower.includes(evTitleLower) ||
                    evTitleLower.includes(issTitleLower) ||
                    evWords.some(w => issTitleLower.includes(w));
    if (isMatch) {
      const targetRow = document.getElementById(`issue-row-${idx}`);
      if (targetRow) {
        targetRow.classList.add('highlighted');
        targetRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        showToast(`Linked Issue Highlighted: ${iss.issue} (Impact: ${formatImpact(iss.impact)})`);
      }
    }
  });
}

// -------------------------------------------------------------
// CARD 5: Offloading Planning (Minimal, Clutter-Free Forecast)
// P10, P50, and P90 rendered cleanly without giant overlapping callouts
// -------------------------------------------------------------
// Builds the offloading planning ECharts option with full confidence bands and tooltip support
function buildCard5OffloadingOption(op, isPopup = false) {
  if (!op) return null;

  const dates = op.dates || [];
  const actualInv = op.actual_inventory || [];
  const p10 = op.p10_early || [];
  const p50 = op.p50_base || [];
  const p90 = op.p90_late || [];

  const currDate = op.current_date || '21 Sep';
  const currInv = op.current_inventory !== undefined ? op.current_inventory : 2.4;
  const targetOffload = op.target_offload !== undefined ? op.target_offload : 3.0;
  const maxCap = op.max_capacity !== undefined ? op.max_capacity : 3.5;
  const unit = op.unit || 'MMbbl';

  const p10Date = op.milestones?.p10?.date || '5 Oct';
  const p50Date = op.milestones?.p50?.date || '8 Oct';
  const p90Date = op.milestones?.p90?.date || '12 Oct';

  // Series names cleanly displaying scenario title and offload date
  const actualSeriesName = 'Actual Inventory';
  const p10SeriesName = `P10 Early (${p10Date})`;
  const p50SeriesName = `P50 Base (${p50Date})`;
  const p90SeriesName = `P90 Late (${p90Date})`;

  // Save series references for Card 6 interactive scenario clicks
  window.card5SeriesNames = {
    p10: p10SeriesName,
    p50: p50SeriesName,
    p90: p90SeriesName,
    actual: actualSeriesName
  };
  window.card5Milestones = {
    p10: p10Date,
    p50: p50Date,
    p90: p90Date,
    currDate: currDate
  };

  // Dynamic Y-axis scale based on maximum data points
  const validActuals = actualInv.filter(v => v !== null && v !== undefined);
  const validP10 = p10.filter(v => v !== null && v !== undefined);
  const maxVal = Math.max(maxCap, targetOffload, ...validActuals, ...validP10, 0.5);
  const yAxisMax = Math.ceil((maxVal * 1.15) * 10) / 10;
  const yInterval = yAxisMax > 10 ? undefined : (yAxisMax > 2 ? 1.0 : (yAxisMax > 1 ? 0.5 : 0.2));

  const option = {
    backgroundColor: '#FFFFFF',
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: 'rgba(15, 23, 42, 0.96)',
      borderColor: '#334155',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#F8FAFC', fontSize: 12, lineHeight: 18 },
      extraCssText: 'border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); pointer-events: none; z-index: 100005;',
      formatter: function (params) {
        if (!params || !params.length) return '';
        let html = `<div style="font-weight: 700; margin-bottom: 6px; color: #94A3B8;">${params[0].name} 2026</div>`;
        params.forEach(p => {
          if (p.value !== null && p.value !== undefined) {
            html += `<div style="display: flex; justify-content: space-between; gap: 16px; margin: 2px 0;">
              <span>${p.marker} ${p.seriesName}</span>
              <span style="font-weight: 600; font-family: monospace;">${Number(p.value).toFixed(2)} ${unit}</span>
            </div>`;
          }
        });
        html += `<div style="margin-top: 6px; padding-top: 4px; border-top: 1px solid #334155; font-size: 11px; color: #F59E0B; display: flex; justify-content: space-between;">
          <span>Target Level:</span>
          <span style="font-weight: 600;">${targetOffload} ${unit}</span>
        </div>`;
        return html;
      }
    },
    legend: {
      data: [actualSeriesName, p10SeriesName, p50SeriesName, p90SeriesName],
      bottom: isPopup ? 38 : 2,
      left: 'center',
      itemGap: 16,
      itemWidth: 14,
      itemHeight: 5,
      icon: 'roundRect',
      textStyle: { color: '#64748B', fontSize: 11, fontWeight: 500 }
    },
    grid: isPopup ? {
      left: '4%',
      right: '4%',
      top: '10%',
      bottom: '16%',
      containLabel: true
    } : {
      left: '3%',
      right: '4%',
      top: '12%',
      bottom: '14%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#CBD5E1' } },
      axisLabel: { color: '#64748B', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      name: `Inventory (${unit})`,
      nameTextStyle: { color: '#64748B', fontSize: 11 },
      min: 0,
      max: yInterval === undefined ? undefined : yAxisMax,
      interval: yInterval,
      splitLine: { lineStyle: { color: '#F1F5F9' } },
      axisLabel: { color: '#64748B', fontSize: 11 }
    },
    series: [
      // 1. P10 Early forecast with Soft Green Confidence Band Area
      {
        name: p10SeriesName,
        type: 'line',
        data: p10,
        lineStyle: { color: '#10B981', type: 'dashed', width: 1.8 },
        itemStyle: { color: '#10B981' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(16, 185, 129, 0.16)' },
            { offset: 1, color: 'rgba(16, 185, 129, 0.03)' }
          ])
        },
        symbol: 'none',
        label: { show: false },
        emphasis: { focus: 'series' }
      },
      // 2. P90 Late forecast with White mask area to shade only confidence band
      {
        name: p90SeriesName,
        type: 'line',
        data: p90,
        lineStyle: { color: '#EF4444', type: 'dashed', width: 1.8 },
        itemStyle: { color: '#EF4444' },
        areaStyle: { color: '#FFFFFF' },
        symbol: 'none',
        label: { show: false },
        emphasis: { focus: 'series' }
      },
      // 3. P50 Base forecast line centered in confidence band
      {
        name: p50SeriesName,
        type: 'line',
        data: p50,
        lineStyle: { color: '#0284C7', type: 'dashed', width: 2.0 },
        itemStyle: { color: '#0284C7' },
        symbol: 'none',
        label: { show: false },
        emphasis: { focus: 'series' }
      },
      // 4. Actual cumulative inventory curve with single clean Target Offload reference line
      {
        name: actualSeriesName,
        type: 'line',
        data: actualInv,
        lineStyle: { color: '#0D9488', width: 2.6 },
        itemStyle: { color: '#0D9488' },
        symbol: 'circle',
        symbolSize: isPopup ? 6 : 5,
        emphasis: { focus: 'series' },
        markLine: {
          symbol: ['none', 'none'],
          silent: true,
          data: [
            {
              yAxis: targetOffload,
              name: 'Target Offload',
              lineStyle: { color: '#F59E0B', type: 'dashed', width: 1.6 },
              label: {
                formatter: `Target (${targetOffload} ${unit})`,
                position: 'insideEndTop',
                color: '#B45309',
                fontSize: 10,
                fontWeight: '600'
              }
            }
          ]
        }
      }
    ]
  };

  if (isPopup) {
    option.dataZoom = [
      {
        type: 'inside',
        start: 0,
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true
      },
      {
        type: 'slider',
        show: true,
        start: 0,
        end: 100,
        bottom: 8,
        height: 28,
        borderColor: '#CBD5E1',
        fillerColor: 'rgba(2, 132, 199, 0.15)',
        handleStyle: {
          color: '#0284C7',
          borderColor: '#0369A1'
        },
        textStyle: { color: '#64748B', fontSize: 11 }
      }
    ];
  }

  return option;
}

// -------------------------------------------------------------
// CARD 5: Offloading Planning (Minimal, Clutter-Free Forecast)
// P10, P50, and P90 rendered cleanly without giant overlapping callouts
// -------------------------------------------------------------
function renderCard5OffloadingPlanning(op) {
  if (!offloadingChart || !op) return;

  const option = buildCard5OffloadingOption(op, false);
  if (!option) return;

  offloadingChart.setOption(option, true);
}

// -------------------------------------------------------------
// CARD 6: Offloading Estimation (Interactive Scenarios)
// Supports field filtering and interactive clicking on P10/P50/P90
// -------------------------------------------------------------
function renderCard6OffloadingEstimation(oe) {
  if (!oe) return;

  const currInv = oe.current_inventory !== undefined ? oe.current_inventory : 2.4;
  const targetOffload = oe.target_offload_level !== undefined ? oe.target_offload_level : 3.0;
  const maxCap = oe.maximum_capacity !== undefined ? oe.maximum_capacity : 3.5;
  const fieldName = oe.field || (dashboardData?.metadata?.selected_field) || 'All Fields';

  const unit = oe.unit || 'MMbbl';
  document.getElementById('stat-curr-inv').innerText = `${currInv} ${unit}`;
  document.getElementById('stat-target-offload').innerText = `${targetOffload} ${unit}`;
  document.getElementById('stat-max-capacity').innerText = maxCap === null ? 'Not reported' : `${maxCap} ${unit}`;

  const fieldBadge = document.getElementById('card6-field-badge');
  if (fieldBadge) {
    fieldBadge.innerText = displayEntity(fieldName);
  }

  const tbody = document.getElementById('offloading-estimation-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  const scenarios = oe.scenarios || [];
  scenarios.forEach((sc) => {
    let pKey = 'p50';
    let tagColorClass = 'p50-color';
    if (sc.scenario.includes('P10')) {
      pKey = 'p10';
      tagColorClass = 'p10-color';
    } else if (sc.scenario.includes('P90')) {
      pKey = 'p90';
      tagColorClass = 'p90-color';
    }

    const tr = document.createElement('tr');
    tr.id = `scenario-row-${pKey}`;
    tr.className = `table-row-interactive scenario-row-clickable ${activeScenarioKey === pKey ? 'active-scenario-' + pKey : ''}`;
    tr.title = `Click to highlight ${sc.scenario} trajectory on Offloading Planning chart`;

    const isSelected = activeScenarioKey === pKey;
    tr.innerHTML = `
      <td class="scenario-tag ${tagColorClass}">
        ${sc.scenario}
        ${isSelected ? ' <span style="font-size: 11px; font-weight: bold;">&#10003;</span>' : ''}
      </td>
      <td style="font-weight: 600;">${sc.estimated_offload_date}</td>
      <td class="${tagColorClass}" style="font-weight: 600;">${sc.days_from_now}</td>
    `;

    tr.onclick = () => toggleScenarioFocus(pKey, sc.scenario, sc.estimated_offload_date);
    tbody.appendChild(tr);
  });
}

function toggleScenarioFocus(pKey, scenarioTitle, dateStr) {
  if (!offloadingChart || !window.card5SeriesNames) return;

  const seriesName = window.card5SeriesNames[pKey];
  const milestoneDate = window.card5Milestones ? window.card5Milestones[pKey] : null;

  if (activeScenarioKey === pKey) {
    // Reset focus
    activeScenarioKey = null;
    document.querySelectorAll('#offloading-estimation-tbody tr').forEach(r => {
      r.classList.remove('active-scenario-p10', 'active-scenario-p50', 'active-scenario-p90');
      const ck = r.querySelector('span');
      if (ck && ck.innerText.includes('✓')) ck.remove();
    });

    offloadingChart.dispatchAction({ type: 'downplay' });
    offloadingChart.dispatchAction({ type: 'hideTip' });
    showToast(`Reset scenario focus to all curves`);
    return;
  }

  // Activate clicked scenario
  activeScenarioKey = pKey;

  document.querySelectorAll('#offloading-estimation-tbody tr').forEach(r => {
    r.classList.remove('active-scenario-p10', 'active-scenario-p50', 'active-scenario-p90');
    const ck = r.querySelector('span');
    if (ck && ck.innerText.includes('✓')) ck.remove();
  });

  const activeRow = document.getElementById(`scenario-row-${pKey}`);
  if (activeRow) {
    activeRow.classList.add(`active-scenario-${pKey}`);
    const tagTd = activeRow.querySelector('.scenario-tag');
    if (tagTd) tagTd.innerHTML += ' <span style="font-size: 11px; font-weight: bold;">&#10003;</span>';
  }

  // Interactively highlight in Chart 5
  offloadingChart.dispatchAction({ type: 'downplay' });
  offloadingChart.dispatchAction({
    type: 'highlight',
    seriesName: seriesName
  });

  if (milestoneDate) {
    offloadingChart.dispatchAction({
      type: 'showTip',
      seriesName: seriesName,
      name: milestoneDate
    });
  }

  showToast(`Focusing on ${scenarioTitle} — Estimated offload: ${dateStr || milestoneDate}`);
}

function setupStatChipsInteractivity() {
  const chipCurrInv = document.getElementById('chip-curr-inv');
  const chipTarget = document.getElementById('chip-target-offload');
  const chipMax = document.getElementById('chip-max-capacity');

  if (chipCurrInv) {
    chipCurrInv.onclick = () => {
      if (offloadingChart && window.card5Milestones?.currDate) {
        offloadingChart.dispatchAction({
          type: 'showTip',
          name: window.card5Milestones.currDate
        });
      }
      showToast(`Current Inventory: ${document.getElementById('stat-curr-inv').innerText}`);
    };
  }

  if (chipTarget) {
    chipTarget.onclick = () => {
      showToast(`Target Offload Level: ${document.getElementById('stat-target-offload').innerText} (Tanker dispatch trigger)`);
    };
  }

  if (chipMax) {
    chipMax.onclick = () => {
      showToast(`Maximum Safe Storage Capacity: ${document.getElementById('stat-max-capacity').innerText}`);
    };
  }
}

// -------------------------------------------------------------
// MODALS CONTROLLER (View All Activities & View All Issues)
// -------------------------------------------------------------
function openActivitiesModal() {
  const modal = document.getElementById('modal-activities');
  if (!modal) return;

  const fieldSelect = document.getElementById('modal-activities-field-filter');
  if (fieldSelect && dashboardData?.metadata?.available_fields) {
    const currFilter = document.getElementById('filter-field')?.value || 'All Fields';
    fieldSelect.innerHTML = '<option value="All Fields">All Fields</option>';
    dashboardData.metadata.available_fields.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f;
      opt.textContent = f;
      if (f === currFilter) opt.selected = true;
      fieldSelect.appendChild(opt);
    });
  }

  filterAndRenderModalActivities();
  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeActivitiesModal() {
  const modal = document.getElementById('modal-activities');
  if (!modal) return;
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

function filterAndRenderModalActivities() {
  const tbody = document.getElementById('modal-activities-tbody');
  if (!tbody) return;

  const searchVal = (document.getElementById('modal-activities-search')?.value || '').toLowerCase().trim();
  const fieldVal = document.getElementById('modal-activities-field-filter')?.value || 'All Fields';
  const statusVal = document.getElementById('modal-activities-status-filter')?.value || 'All';

  const source = (masterActivities && masterActivities.length) ? masterActivities : (dashboardData?.planned_activities || []);

  const filtered = source.filter(act => {
    if (searchVal) {
      const actText = `${act.date} ${act.activity} ${act.field} ${act.expected_impact} ${act.status}`.toLowerCase();
      if (!actText.includes(searchVal)) return false;
    }
    if (fieldVal !== 'All Fields' && act.field !== fieldVal) return false;
    if (statusVal !== 'All' && act.status !== statusVal) return false;
    return true;
  });

  // Sort modal activities
  filtered.sort((a, b) => {
    let valA, valB;
    if (modalActSortCol === 'date') {
      valA = parseDateToSortValue(a.date);
      valB = parseDateToSortValue(b.date);
      return modalActSortAsc ? valA - valB : valB - valA;
    } else if (modalActSortCol === 'expected_impact' || modalActSortCol === 'impact') {
      const numA = parseFloat((String(a.expected_impact || a.impact || '0').match(/-?\d+(?:\.\d+)?/) || [0])[0]);
      const numB = parseFloat((String(b.expected_impact || b.impact || '0').match(/-?\d+(?:\.\d+)?/) || [0])[0]);
      return modalActSortAsc ? numA - numB : numB - numA;
    } else {
      valA = String(a[modalActSortCol] || '').toLowerCase();
      valB = String(b[modalActSortCol] || '').toLowerCase();
      return modalActSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
  });

  // Update modal header sort indicator icons
  ['date', 'activity', 'field', 'expected_impact', 'status'].forEach(col => {
    const icon = document.getElementById(`sort-modal-act-${col}`);
    if (icon) {
      icon.textContent = (modalActSortCol === col) ? (modalActSortAsc ? '▲' : '▼') : '';
    }
  });

  tbody.innerHTML = '';
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #94A3B8; padding: 26px;">No planned activities match the current filters.</td></tr>`;
  } else {
    filtered.forEach((act) => {
      const tr = document.createElement('tr');
      let pillClass = 'pill-blue';
      if (act.status === 'In Progress') pillClass = 'pill-amber';
      else if (act.status === 'Completed') pillClass = 'pill-green';
      else if (act.status === 'Deferred') pillClass = 'pill-slate';

      const origIdx = source.indexOf(act);

      tr.innerHTML = `
        <td style="color: #64748B; font-size: 11px; white-space: nowrap;">${act.date}</td>
        <td style="font-weight: 600;">${act.activity}</td>
        <td><span class="badge-pill pill-slate">${act.field}</span></td>
        <td style="color: #EF4444; font-weight: 600;">${formatImpact(act.expected_impact || act.impact)}</td>
        <td>
          <div class="status-dropdown-wrap">
            <button class="status-badge-btn ${pillClass}" onclick="toggleModalActivityMenu(event, ${origIdx})">
              <span>${act.status}</span>
              <span class="status-caret">&#9660;</span>
            </button>
            <div id="modal-act-menu-${origIdx}" class="status-menu-popup">
              <button class="status-menu-item" onclick="setModalActivityStatus(${origIdx}, 'Planned', 'pill-blue')">
                <span class="status-dot status-dot-blue"></span> Planned
              </button>
              <button class="status-menu-item" onclick="setModalActivityStatus(${origIdx}, 'In Progress', 'pill-amber')">
                <span class="status-dot status-dot-amber"></span> In Progress
              </button>
              <button class="status-menu-item" onclick="setModalActivityStatus(${origIdx}, 'Completed', 'pill-green')">
                <span class="status-dot status-dot-green"></span> Completed
              </button>
              <button class="status-menu-item" onclick="setModalActivityStatus(${origIdx}, 'Deferred', 'pill-slate')">
                <span class="status-dot status-dot-slate"></span> Deferred
              </button>
            </div>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  const countBadge = document.getElementById('modal-activities-count');
  if (countBadge) countBadge.innerText = `${filtered.length} records`;

  const footerStats = document.getElementById('modal-activities-footer-stats');
  if (footerStats) footerStats.innerText = `Showing ${filtered.length} of ${source.length} activities`;
}

window.sortModalActivities = function(col) {
  if (modalActSortCol === col) {
    modalActSortAsc = !modalActSortAsc;
  } else {
    modalActSortCol = col;
    modalActSortAsc = true;
  }
  filterAndRenderModalActivities();
};

function toggleModalActivityMenu(event, idx) {
  event.stopPropagation();
  document.querySelectorAll('.status-menu-popup').forEach(m => {
    if (m.id !== `modal-act-menu-${idx}`) m.classList.remove('active');
  });
  const menu = document.getElementById(`modal-act-menu-${idx}`);
  if (menu) menu.classList.toggle('active');
}

function setModalActivityStatus(origIdx, newStatus, pillClass) {
  const menu = document.getElementById(`modal-act-menu-${origIdx}`);
  if (menu) menu.classList.remove('active');

  const source = (masterActivities && masterActivities.length) ? masterActivities : (dashboardData?.planned_activities || []);
  if (source[origIdx]) {
    source[origIdx].status = newStatus;
  }

  if (dashboardData?.planned_activities) {
    const act = source[origIdx];
    const match = dashboardData.planned_activities.find(a => a.activity === act.activity && a.date === act.date);
    if (match) match.status = newStatus;
    renderCard3PlannedActivities(dashboardData.planned_activities);
  }

  filterAndRenderModalActivities();

  fetch('/api/activity_status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index: origIdx, status: newStatus, view: currentView })
  }).then(() => {
    showToast(`Activity status set to ${newStatus}`);
  }).catch(err => console.error('Status sync error:', err));
}

function openIssuesModal() {
  const modal = document.getElementById('modal-issues');
  if (!modal) return;

  const fieldSelect = document.getElementById('modal-issues-field-filter');
  if (fieldSelect && dashboardData?.metadata?.available_fields) {
    const currFilter = document.getElementById('filter-field')?.value || 'All Fields';
    fieldSelect.innerHTML = '<option value="All Fields">All Fields</option>';
    dashboardData.metadata.available_fields.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f;
      opt.textContent = f;
      if (f === currFilter) opt.selected = true;
      fieldSelect.appendChild(opt);
    });
  }

  filterAndRenderModalIssues();
  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeIssuesModal() {
  const modal = document.getElementById('modal-issues');
  if (!modal) return;
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

function filterAndRenderModalIssues() {
  const tbody = document.getElementById('modal-issues-tbody');
  if (!tbody) return;

  const searchVal = (document.getElementById('modal-issues-search')?.value || '').toLowerCase().trim();
  const fieldVal = document.getElementById('modal-issues-field-filter')?.value || 'All Fields';
  const statusVal = document.getElementById('modal-issues-status-filter')?.value || 'All';

  const source = (masterIssues && masterIssues.length) ? masterIssues : (dashboardData?.active_issues || []);

  const filtered = source.filter(iss => {
    if (searchVal) {
      const issText = `${iss.issue} ${iss.field} ${iss.impact} ${iss.status} ${iss.recovery || ''} ${iss.description || ''} ${iss.remarks || ''}`.toLowerCase();
      if (!issText.includes(searchVal)) return false;
    }
    if (fieldVal !== 'All Fields' && iss.field !== fieldVal) return false;
    if (statusVal !== 'All' && iss.status !== statusVal) return false;
    return true;
  });

  // Sort modal issues
  filtered.sort((a, b) => {
    let valA, valB;
    if (modalIssSortCol === 'recovery' || modalIssSortCol === 'date') {
      valA = parseDateToSortValue(getIssueSortDate(a));
      valB = parseDateToSortValue(getIssueSortDate(b));
      return modalIssSortAsc ? valA - valB : valB - valA;
    } else if (modalIssSortCol === 'impact') {
      const numA = parseFloat((String(a.impact || '0').match(/-?\d+(?:\.\d+)?/) || [0])[0]);
      const numB = parseFloat((String(b.impact || '0').match(/-?\d+(?:\.\d+)?/) || [0])[0]);
      return modalIssSortAsc ? numA - numB : numB - numA;
    } else {
      valA = String(a[modalIssSortCol] || '').toLowerCase();
      valB = String(b[modalIssSortCol] || '').toLowerCase();
      return modalIssSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
  });

  // Update modal header sort indicator icons
  ['issue', 'field', 'impact', 'status', 'recovery'].forEach(col => {
    const icon = document.getElementById(`sort-modal-iss-${col}`);
    if (icon) {
      icon.textContent = (modalIssSortCol === col) ? (modalIssSortAsc ? '▲' : '▼') : '';
    }
  });

  tbody.innerHTML = '';
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #94A3B8; padding: 26px;">No operational issues match the current filters.</td></tr>`;
  } else {
    filtered.forEach((iss) => {
      const tr = document.createElement('tr');
      let pillClass = 'pill-red';
      if (iss.status === 'Monitoring') pillClass = 'pill-blue';
      else if (iss.status === 'In Progress') pillClass = 'pill-amber';
      else if (iss.status === 'Closed') pillClass = 'pill-green';
      else if (iss.status === 'Open') pillClass = 'pill-red';

      const origIdx = source.indexOf(iss);

      tr.innerHTML = `
        <td style="font-weight: 600;">${iss.issue}</td>
        <td><span class="badge-pill pill-slate">${iss.field}</span></td>
        <td style="color: #EF4444; font-weight: 600;">${formatImpact(iss.impact)}</td>
        <td>
          <div class="status-dropdown-wrap">
            <button class="status-badge-btn ${pillClass}" onclick="toggleModalIssueMenu(event, ${origIdx})">
              <span>${iss.status}</span>
              <span class="status-caret">&#9660;</span>
            </button>
            <div id="modal-iss-menu-${origIdx}" class="status-menu-popup">
              <button class="status-menu-item" onclick="setModalIssueStatus(${origIdx}, 'Open', 'pill-red')">
                <span class="status-dot status-dot-red"></span> Open
              </button>
              <button class="status-menu-item" onclick="setModalIssueStatus(${origIdx}, 'In Progress', 'pill-amber')">
                <span class="status-dot status-dot-amber"></span> In Progress
              </button>
              <button class="status-menu-item" onclick="setModalIssueStatus(${origIdx}, 'Monitoring', 'pill-blue')">
                <span class="status-dot status-dot-blue"></span> Monitoring
              </button>
              <button class="status-menu-item" onclick="setModalIssueStatus(${origIdx}, 'Closed', 'pill-green')">
                <span class="status-dot status-dot-green"></span> Closed
              </button>
            </div>
          </div>
        </td>
        <td style="font-size: 11px; color: #334155;">${iss.recovery || '—'}</td>
        <td style="font-size: 11px; color: #64748B;">${iss.description || iss.remarks || 'Standard operations'}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  const countBadge = document.getElementById('modal-issues-count');
  if (countBadge) countBadge.innerText = `${filtered.length} records`;

  const footerStats = document.getElementById('modal-issues-footer-stats');
  if (footerStats) footerStats.innerText = `Showing ${filtered.length} of ${source.length} issues`;
}

window.sortModalIssues = function(col) {
  if (modalIssSortCol === col) {
    modalIssSortAsc = !modalIssSortAsc;
  } else {
    modalIssSortCol = col;
    modalIssSortAsc = true;
  }
  filterAndRenderModalIssues();
};

function toggleModalIssueMenu(event, idx) {
  event.stopPropagation();
  document.querySelectorAll('.status-menu-popup').forEach(m => {
    if (m.id !== `modal-iss-menu-${idx}`) m.classList.remove('active');
  });
  const menu = document.getElementById(`modal-iss-menu-${idx}`);
  if (menu) menu.classList.toggle('active');
}

function setModalIssueStatus(origIdx, newStatus, pillClass) {
  const menu = document.getElementById(`modal-iss-menu-${origIdx}`);
  if (menu) menu.classList.remove('active');

  const source = (masterIssues && masterIssues.length) ? masterIssues : (dashboardData?.active_issues || []);
  if (source[origIdx]) {
    source[origIdx].status = newStatus;
  }

  if (dashboardData?.active_issues) {
    const iss = source[origIdx];
    const match = dashboardData.active_issues.find(i => i.issue === iss.issue && i.field === iss.field);
    if (match) match.status = newStatus;
    renderCard4ActiveIssues(dashboardData.active_issues);
  }

  filterAndRenderModalIssues();

  fetch('/api/issue_status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index: origIdx, status: newStatus, view: currentView })
  }).then(() => {
    showToast(`Issue status set to ${newStatus}`);
  }).catch(err => console.error('Status sync error:', err));
}

// -------------------------------------------------------------
// MODAL 3: Interactive Chart Popup & Deep Zoom Controller
// -------------------------------------------------------------
function openChartPopup(chartType) {
  const modal = document.getElementById('modal-chart-popup');
  if (!modal || !dashboardData) return;

  activePopupChartType = chartType;

  const titleEl = document.getElementById('modal-chart-title');
  const subEl = document.getElementById('modal-chart-subtitle');
  const badgeEl = document.getElementById('modal-chart-badge');
  const selectedField = dashboardData.metadata?.selected_field || 'All Fields';

  let chartOption = null;

  if (chartType === 'trend') {
    if (titleEl) titleEl.innerText = `Production Trend — ${selectedField}`;
    if (subEl) subEl.innerText = 'Pan across dates, zoom in on data points, and inspect operational issue remarks.';
    if (badgeEl) badgeEl.innerText = `Card 1 • ${selectedField}`;

    const pt = dashboardData.production_trend;
    const activeIssues = dashboardData.active_issues || [];
    const plannedActivities = dashboardData.planned_activities || [];
    chartOption = buildCard1ProductionTrendOption(pt, activeIssues, selectedField, plannedActivities, true);
  } else if (chartType === 'offloading') {
    if (titleEl) titleEl.innerText = 'Offloading Planning & Inventory Forecast';
    if (subEl) subEl.innerText = 'Interactive confidence bands (P10, P50, P90) with target offload threshold.';
    if (badgeEl) badgeEl.innerText = 'Card 5 • Inventory Tracking';

    chartOption = buildCard5OffloadingOption(dashboardData.offloading_planning, true);
  }

  if (!chartOption) return;

  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';

  const popupDom = document.getElementById('popupChart');
  if (!popupChart && popupDom) {
    popupChart = echarts.init(popupDom);
  }

  if (popupChart) {
    popupChart.clear();
    popupChart.setOption(chartOption, true);

    if (chartType === 'trend') {
      popupChart.off('click');
      popupChart.on('click', function (params) {
        const date = params.name;
        const pt = dashboardData.production_trend || {};
        const ctx = getTrendContextForDate(
          date,
          pt.events || [],
          dashboardData.active_issues || [],
          selectedField,
          dashboardData.planned_activities || []
        );
        if (ctx.matchedIssues.length > 0) {
          highlightLinkedIssue(ctx.matchedIssues[0].issue);
        } else if (ctx.matchedEvent) {
          highlightLinkedIssue(ctx.matchedEvent.title);
        }
      });
    }

    setTimeout(() => {
      if (popupChart) popupChart.resize();
    }, 120);
  }
}

function closeChartPopup() {
  const modal = document.getElementById('modal-chart-popup');
  if (!modal) return;
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
  activePopupChartType = null;
}

function zoomInChart() {
  if (!popupChart) return;
  const opt = popupChart.getOption();
  const dz = (opt.dataZoom && opt.dataZoom[0]) || { start: 0, end: 100 };
  const curStart = (dz.start !== undefined) ? dz.start : 0;
  const curEnd = (dz.end !== undefined) ? dz.end : 100;
  const span = curEnd - curStart;
  const newSpan = Math.max(10, span * 0.7); // 30% zoom in
  const center = (curStart + curEnd) / 2;
  const newStart = Math.max(0, Math.round(center - newSpan / 2));
  const newEnd = Math.min(100, Math.round(center + newSpan / 2));

  popupChart.dispatchAction({
    type: 'dataZoom',
    start: newStart,
    end: newEnd
  });
}

function zoomOutChart() {
  if (!popupChart) return;
  const opt = popupChart.getOption();
  const dz = (opt.dataZoom && opt.dataZoom[0]) || { start: 0, end: 100 };
  const curStart = (dz.start !== undefined) ? dz.start : 0;
  const curEnd = (dz.end !== undefined) ? dz.end : 100;
  const span = curEnd - curStart;
  const newSpan = Math.min(100, span / 0.7); // zoom out
  const center = (curStart + curEnd) / 2;
  const newStart = Math.max(0, Math.round(center - newSpan / 2));
  const newEnd = Math.min(100, Math.round(center + newSpan / 2));

  popupChart.dispatchAction({
    type: 'dataZoom',
    start: newStart,
    end: newEnd
  });
}

function resetZoomChart() {
  if (!popupChart) return;
  popupChart.dispatchAction({
    type: 'dataZoom',
    start: 0,
    end: 100
  });
  showToast('Zoom reset to 100% full view');
}

function exportChartPng() {
  if (!popupChart) return;
  const url = popupChart.getDataURL({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: '#FFFFFF'
  });
  const a = document.createElement('a');
  a.href = url;
  a.download = `${activePopupChartType || 'chart'}_high_res_${Date.now()}.png`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast('Chart exported as high-resolution PNG');
}

// -------------------------------------------------------------
// Filter Handlers & Excel Ingestion
// -------------------------------------------------------------
function filterByField(fieldName) {
  const select = document.getElementById('filter-field');
  if (select) select.value = fieldName;
  fetchDashboardData(fieldName);
  showToast(`Filtered dashboard to: ${fieldName}`);
}

async function applyFilters() {
  const period = document.getElementById('filter-period').value;
  const field = document.getElementById('filter-field').value;
  const facility = document.getElementById('filter-facility').value;

  try {
    const res = await fetch('/api/filter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ period, field, facility })
    });
    if (!res.ok) throw new Error('Filter update failed');
    fetchDashboardData(field);
    showToast('Filters applied successfully.');
  } catch (err) {
    showToast(`Failed to apply filters: ${err.message}`);
  }
}

async function handleExcelUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  try {
    showToast(`Ingesting ${file.name} workbook...`);
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || 'Upload error');

    showToast(`Success! Ingested ${result.sheets_parsed} sheet(s). Updating field picklist...`);
    await setView('field');
  } catch (err) {
    showToast(`Upload failed: ${err.message}`);
  } finally {
    event.target.value = '';
  }
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.innerText = msg;
  toast.style.display = 'block';
  setTimeout(() => {
    toast.style.display = 'none';
  }, 4000);
}

// -------------------------------------------------------------
// Interactive Period Picker Controller
// Supports: Month Picker, Single Date Picker, and Date Range Picker
// -------------------------------------------------------------
const monthNamesShort = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const monthNamesLong = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

const periodPickerState = {
  mode: 'month', // 'month' | 'single' | 'range'
  year: 2026,
  monthIndex: 8, // September (0-based)
  calYear: 2026,
  calMonthIndex: 8, // September
  selectedSingleDate: '21 Sep 2026',
  rangeStartDate: '1 Sep 2026',
  rangeEndDate: '21 Sep 2026',
  tempRangeStart: '1 Sep 2026',
  tempRangeEnd: '21 Sep 2026',
  selectedMonthDisplay: 'Sep 2026'
};

function initPeriodPicker() {
  const triggerBtn = document.getElementById('period-picker-btn');
  const popup = document.getElementById('period-popup');
  if (!triggerBtn || !popup) return;

  // Toggle popup on click
  triggerBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    popup.classList.toggle('show');
  });

  // Close popup when clicking outside
  document.addEventListener('click', (e) => {
    if (!popup.contains(e.target) && !triggerBtn.contains(e.target)) {
      popup.classList.remove('show');
    }
  });

  // Tab mode switching (Month, Single Date, Date Range)
  const tabs = document.querySelectorAll('.popup-mode-tabs .mode-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const mode = tab.getAttribute('data-mode');
      setPickerMode(mode);
    });
  });

  // Presets
  const presetChips = document.querySelectorAll('.popup-preset-chips .chip-btn');
  presetChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const preset = chip.getAttribute('data-preset');
      applyPresetSelection(preset);
    });
  });

  // Year navigation in Month view
  document.getElementById('btn-year-prev')?.addEventListener('click', () => {
    periodPickerState.year--;
    renderMonthsPickerGrid();
  });
  document.getElementById('btn-year-next')?.addEventListener('click', () => {
    periodPickerState.year++;
    renderMonthsPickerGrid();
  });

  // Month navigation in Calendar view
  document.getElementById('btn-cal-prev')?.addEventListener('click', () => {
    periodPickerState.calMonthIndex--;
    if (periodPickerState.calMonthIndex < 0) {
      periodPickerState.calMonthIndex = 11;
      periodPickerState.calYear--;
    }
    renderCalendarDaysGrid();
  });
  document.getElementById('btn-cal-next')?.addEventListener('click', () => {
    periodPickerState.calMonthIndex++;
    if (periodPickerState.calMonthIndex > 11) {
      periodPickerState.calMonthIndex = 0;
      periodPickerState.calYear++;
    }
    renderCalendarDaysGrid();
  });

  // Cancel & Apply buttons
  document.getElementById('btn-cancel-period')?.addEventListener('click', () => {
    popup.classList.remove('show');
  });
  document.getElementById('btn-confirm-period')?.addEventListener('click', applyPeriodSelection);

  // Initial render of picker sub-views
  renderMonthsPickerGrid();
  renderCalendarDaysGrid();
}

function setPickerMode(mode) {
  periodPickerState.mode = mode;

  // Update tabs active class
  document.querySelectorAll('.popup-mode-tabs .mode-tab').forEach(t => {
    t.classList.toggle('active', t.getAttribute('data-mode') === mode);
  });

  // Switch visible view
  const monthView = document.getElementById('popup-view-month');
  const calView = document.getElementById('popup-view-calendar');
  const hintEl = document.getElementById('calendar-hint');

  if (mode === 'month') {
    monthView.classList.add('active');
    calView.classList.remove('active');
  } else {
    monthView.classList.remove('active');
    calView.classList.add('active');

    if (mode === 'single') {
      hintEl.innerText = 'Single Date Mode: Click any date to select without range';
    } else {
      hintEl.innerText = 'Range Mode: Click a start date, then click an end date';
    }
    renderCalendarDaysGrid();
  }
}

function renderMonthsPickerGrid() {
  const labelYear = document.getElementById('label-picker-year');
  if (labelYear) labelYear.innerText = periodPickerState.year;

  const grid = document.getElementById('months-grid');
  if (!grid) return;
  grid.innerHTML = '';

  monthNamesShort.forEach((mName, idx) => {
    const cell = document.createElement('div');
    cell.className = 'month-cell';
    if (idx === periodPickerState.monthIndex && periodPickerState.year === 2026) {
      cell.classList.add('selected');
    }
    cell.innerText = mName;
    cell.addEventListener('click', () => {
      periodPickerState.monthIndex = idx;
      periodPickerState.selectedMonthDisplay = `${mName} ${periodPickerState.year}`;
      // Highlight cell
      document.querySelectorAll('#months-grid .month-cell').forEach(c => c.classList.remove('selected'));
      cell.classList.add('selected');
    });
    grid.appendChild(cell);
  });
}

function renderCalendarDaysGrid() {
  const labelTitle = document.getElementById('label-cal-month-year');
  if (labelTitle) {
    labelTitle.innerText = `${monthNamesLong[periodPickerState.calMonthIndex]} ${periodPickerState.calYear}`;
  }

  const daysGrid = document.getElementById('calendar-days-grid');
  if (!daysGrid) return;
  daysGrid.innerHTML = '';

  const y = periodPickerState.calYear;
  const m = periodPickerState.calMonthIndex;
  const firstDayWeekday = new Date(y, m, 1).getDay(); // 0 is Sun
  const totalDaysInMonth = new Date(y, m + 1, 0).getDate();

  // Empty leading cells
  for (let i = 0; i < firstDayWeekday; i++) {
    const empty = document.createElement('div');
    empty.className = 'day-cell empty';
    daysGrid.appendChild(empty);
  }

  // Days in month
  for (let day = 1; day <= totalDaysInMonth; day++) {
    const dayDateStr = `${day} ${monthNamesShort[m]} ${y}`;
    const cell = document.createElement('div');
    cell.className = 'day-cell';
    cell.innerText = day;

    if (periodPickerState.mode === 'single') {
      if (dayDateStr === periodPickerState.selectedSingleDate) {
        cell.classList.add('selected');
      }
    } else if (periodPickerState.mode === 'range') {
      const curDateObj = new Date(y, m, day);
      const startObj = parseDateToObj(periodPickerState.tempRangeStart);
      const endObj = parseDateToObj(periodPickerState.tempRangeEnd);

      if (startObj && !endObj && curDateObj.getTime() === startObj.getTime()) {
        cell.classList.add('selected');
      } else if (startObj && endObj) {
        if (curDateObj.getTime() === startObj.getTime()) {
          cell.classList.add('range-start');
        } else if (curDateObj.getTime() === endObj.getTime()) {
          cell.classList.add('range-end');
        } else if (curDateObj > startObj && curDateObj < endObj) {
          cell.classList.add('in-range');
        }
      }
    }

    cell.addEventListener('click', () => handleDayCellClick(day, m, y));
    daysGrid.appendChild(cell);
  }
}

function handleDayCellClick(day, m, y) {
  const clickedDateStr = `${day} ${monthNamesShort[m]} ${y}`;
  const hintEl = document.getElementById('calendar-hint');

  if (periodPickerState.mode === 'single') {
    periodPickerState.selectedSingleDate = clickedDateStr;
    hintEl.innerText = `Selected Single Date: ${clickedDateStr}`;
    renderCalendarDaysGrid();
  } else if (periodPickerState.mode === 'range') {
    if (!periodPickerState.tempRangeStart || (periodPickerState.tempRangeStart && periodPickerState.tempRangeEnd)) {
      // First click: start of range
      periodPickerState.tempRangeStart = clickedDateStr;
      periodPickerState.tempRangeEnd = null;
      hintEl.innerText = `Range Start: ${clickedDateStr}. Now click an end date.`;
    } else {
      // Second click: end of range
      const startObj = parseDateToObj(periodPickerState.tempRangeStart);
      const clickedObj = new Date(y, m, day);

      if (clickedObj < startObj) {
        // Swap if clicked earlier
        periodPickerState.tempRangeEnd = periodPickerState.tempRangeStart;
        periodPickerState.tempRangeStart = clickedDateStr;
      } else {
        periodPickerState.tempRangeEnd = clickedDateStr;
      }
      periodPickerState.rangeStartDate = periodPickerState.tempRangeStart;
      periodPickerState.rangeEndDate = periodPickerState.tempRangeEnd;
      hintEl.innerText = `Selected Range: ${periodPickerState.rangeStartDate} – ${periodPickerState.rangeEndDate}`;
    }
    renderCalendarDaysGrid();
  }
}

function parseDateToObj(str) {
  if (!str) return null;
  const parts = str.split(' ');
  if (parts.length < 3) return null;
  const d = parseInt(parts[0], 10);
  const m = monthNamesShort.indexOf(parts[1]);
  const y = parseInt(parts[2], 10);
  return new Date(y, m, d);
}

function applyPresetSelection(preset) {
  if (preset === 'month-sep') {
    setPickerMode('month');
    periodPickerState.year = 2026;
    periodPickerState.monthIndex = 8;
    periodPickerState.selectedMonthDisplay = 'Sep 2026';
    renderMonthsPickerGrid();
  } else if (preset === 'mtd') {
    setPickerMode('range');
    periodPickerState.tempRangeStart = '1 Sep 2026';
    periodPickerState.tempRangeEnd = '21 Sep 2026';
    periodPickerState.rangeStartDate = '1 Sep 2026';
    periodPickerState.rangeEndDate = '21 Sep 2026';
    renderCalendarDaysGrid();
  } else if (preset === 'last-7') {
    setPickerMode('range');
    periodPickerState.tempRangeStart = '15 Sep 2026';
    periodPickerState.tempRangeEnd = '21 Sep 2026';
    periodPickerState.rangeStartDate = '15 Sep 2026';
    periodPickerState.rangeEndDate = '21 Sep 2026';
    renderCalendarDaysGrid();
  } else if (preset === 'single-latest') {
    setPickerMode('single');
    periodPickerState.selectedSingleDate = '21 Sep 2026';
    renderCalendarDaysGrid();
  }
  applyPeriodSelection();
}

function applyPeriodSelection() {
  let periodText = 'Sep 2026';

  if (periodPickerState.mode === 'month') {
    periodText = periodPickerState.selectedMonthDisplay;
  } else if (periodPickerState.mode === 'single') {
    periodText = periodPickerState.selectedSingleDate;
  } else if (periodPickerState.mode === 'range') {
    if (periodPickerState.tempRangeStart && periodPickerState.tempRangeEnd) {
      periodText = `${periodPickerState.tempRangeStart} – ${periodPickerState.tempRangeEnd}`;
    } else {
      periodText = periodPickerState.tempRangeStart || 'Sep 2026';
    }
  }

  // Update UI display button and hidden input
  document.getElementById('period-display-text').innerText = periodText;
  document.getElementById('filter-period').value = periodText;

  // Close popup
  document.getElementById('period-popup')?.classList.remove('show');

  // Trigger apply filters
  applyFilters();
  showToast(`Period updated to: ${periodText}`);
}
