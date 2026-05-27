(() => {
  "use strict";

  function slugify(text) {
    return (text || "")
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-");
  }

  function asNumber(text) {
    const cleaned = (text || "").replace(/[^0-9.-]/g, "");
    if (!cleaned) {
      return null;
    }
    const n = Number(cleaned);
    return Number.isFinite(n) ? n : null;
  }

  function ensureHeadingIds() {
    const headings = Array.from(document.querySelectorAll("main.content h2"));
    headings.forEach((h, idx) => {
      if (!h.id) {
        const base = slugify(h.textContent) || `section-${idx + 1}`;
        let id = base;
        let bump = 2;
        while (document.getElementById(id)) {
          id = `${base}-${bump}`;
          bump += 1;
        }
        h.id = id;
      }
    });
    return headings;
  }

  function buildSectionNavigator(headings) {
    if (!headings.length) {
      return;
    }
    const host = document.querySelector("main.content");
    if (!host) {
      return;
    }

    const nav = document.createElement("div");
    nav.className = "section-nav";
    nav.innerHTML = '<div class="section-nav-label">Jump to</div><div class="section-nav-chips"></div>';
    const chipWrap = nav.querySelector(".section-nav-chips");

    headings.forEach((h) => {
      const a = document.createElement("a");
      a.className = "section-chip";
      a.href = `#${h.id}`;
      a.textContent = h.textContent.trim();
      chipWrap.appendChild(a);
    });

    const titleBlock = document.getElementById("title-block-header");
    if (titleBlock && titleBlock.parentElement) {
      titleBlock.parentElement.insertBefore(nav, titleBlock.nextSibling);
    } else {
      host.insertBefore(nav, host.firstChild);
    }
  }

  function sortTableByColumn(table, colIdx, ascending) {
    const tbody = table.querySelector("tbody");
    if (!tbody) {
      return;
    }
    const rows = Array.from(tbody.querySelectorAll("tr"));

    rows.sort((a, b) => {
      const at = (a.children[colIdx]?.innerText || "").trim();
      const bt = (b.children[colIdx]?.innerText || "").trim();
      const an = asNumber(at);
      const bn = asNumber(bt);

      let cmp;
      if (an !== null && bn !== null) {
        cmp = an - bn;
      } else {
        cmp = at.localeCompare(bt, undefined, { numeric: true, sensitivity: "base" });
      }
      return ascending ? cmp : -cmp;
    });

    rows.forEach((r) => tbody.appendChild(r));
  }

  function addTableEnhancements() {
    const tables = Array.from(document.querySelectorAll("table.adoption-table"));
    const tableStates = [];
    const departmentValues = new Set();
    const excludedDepartments = new Set();
    let departmentMode = "exclude";

    const scopeStats = {
      totalHeadcount: 0,
      totalWithLicense: 0,
      deptRows: [],
    };

    const kpiState = {
      license: null,
      noTools: null,
    };

    const insightState = {
      grid: null,
    };

    function isDepartmentTable(headers) {
      return headers.some((h) => /department|business\s*unit/i.test((h.innerText || "").trim()));
    }

    function departmentColumnIndex(headers) {
      const idx = headers.findIndex((h) => /department|business\s*unit/i.test((h.innerText || "").trim()));
      return idx >= 0 ? idx : null;
    }

    function inScopeDepartment(dept) {
      if (!excludedDepartments.size) {
        return true;
      }
      if (departmentMode === "include") {
        return excludedDepartments.has(dept);
      }
      return !excludedDepartments.has(dept);
    }

    function parseIntSafe(value) {
      const n = Number.parseInt((value || "").replace(/[^0-9-]/g, ""), 10);
      return Number.isFinite(n) ? n : 0;
    }

    function parseDepartmentStats() {
      const deptTable = tableStates.find((state) => state.metrics);
      if (!deptTable) {
        return;
      }

      const rows = [];
      deptTable.bodyRows.forEach((row) => {
        const dept = (row.children[deptTable.deptColIdx]?.innerText || "").trim();
        const headcount = parseIntSafe(row.children[deptTable.metrics.headIdx]?.innerText || "0");
        const withLicense = parseIntSafe(row.children[deptTable.metrics.withLicIdx]?.innerText || "0");
        if (!dept) {
          return;
        }
        rows.push({ dept, headcount, withLicense });
      });

      scopeStats.deptRows = rows;
      scopeStats.totalHeadcount = rows.reduce((acc, r) => acc + r.headcount, 0);
      scopeStats.totalWithLicense = rows.reduce((acc, r) => acc + r.withLicense, 0);
    }

    function currentScopeRows() {
      return scopeStats.deptRows.filter((r) => inScopeDepartment(r.dept));
    }

    function renderScopedKpis() {
      if (!kpiState.license || !kpiState.noTools) {
        return;
      }

      const rows = currentScopeRows();
      const total = rows.reduce((acc, r) => acc + r.headcount, 0);
      const withLicense = rows.reduce((acc, r) => acc + r.withLicense, 0);
      const noTools = Math.max(total - withLicense, 0);
      const pct = total ? (withLicense / total) * 100 : 0;
      const noToolsPct = total ? (noTools / total) * 100 : 0;

      kpiState.license.valueEl.textContent = `${Math.round(pct)}%`;
      kpiState.license.subEl.textContent = `${withLicense} of ${total} employees (scoped)`;

      kpiState.noTools.valueEl.textContent = String(noTools);
      kpiState.noTools.subEl.textContent = `${Math.round(noToolsPct)}% of scope - priority activation`;
    }

    function renderScopedInsights() {
      if (!insightState.grid) {
        return;
      }

      const rows = currentScopeRows();
      const total = rows.reduce((acc, r) => acc + r.headcount, 0);
      const withLicense = rows.reduce((acc, r) => acc + r.withLicense, 0);
      const noTools = Math.max(total - withLicense, 0);
      const adoptionPct = total ? (withLicense / total) * 100 : 0;
      const noToolsPct = total ? (noTools / total) * 100 : 0;

      const topBus = rows.filter((r) => r.headcount && (r.withLicense / r.headcount) * 100 >= 99.5).map((r) => r.dept);
      const midBus = rows.filter((r) => {
        if (!r.headcount) {
          return false;
        }
        const p = (r.withLicense / r.headcount) * 100;
        return p >= 50 && p < 80;
      });
      const lowBus = rows.filter((r) => {
        if (!r.headcount) {
          return false;
        }
        const p = (r.withLicense / r.headcount) * 100;
        return p > 0 && p < 50;
      });
      const zeroBus = rows.filter((r) => r.headcount > 0 && r.withLicense === 0);

      const bits = [];
      if (topBus.length) {
        const names = topBus.slice(0, 3).join(", ") + (topBus.length > 3 ? "..." : "");
        bits.push(
          `<div class="insight insight-green"><span class="insight-icon">🟢</span><div><div class="insight-headline">${topBus.length} BUs at 100% adoption (scoped)</div><div class="insight-detail">${names} fully equipped.</div></div></div>`
        );
      }

      bits.push(
        `<div class="insight insight-amber"><span class="insight-icon">🟡</span><div><div class="insight-headline">${midBus.length} BUs at 50-79% adoption (scoped)</div><div class="insight-detail">Mid-adoption departments in current filter scope.</div></div></div>`
      );

      const needsActivation = lowBus.length + zeroBus.length;
      bits.push(
        `<div class="insight insight-red"><span class="insight-icon">🔴</span><div><div class="insight-headline">${needsActivation} BUs need activation (scoped)</div><div class="insight-detail">${zeroBus.length} at 0%, ${lowBus.length} below 50%.</div></div></div>`
      );

      bits.push(
        `<div class="insight insight-blue"><span class="insight-icon">📊</span><div><div class="insight-headline">${adoptionPct.toFixed(1)}% scoped license adoption</div><div class="insight-detail">${withLicense} of ${total} employees in selected scope.</div></div></div>`
      );

      bits.push(
        `<div class="insight insight-amber"><span class="insight-icon">🎯</span><div><div class="insight-headline">${noTools} employees (${Math.round(noToolsPct)}%) have zero tools (scoped)</div><div class="insight-detail">Scoped activation cohort for the next cycle.</div></div></div>`
      );

      insightState.grid.innerHTML = bits.join("");
    }

    function refreshScopedSummaries() {
      renderScopedKpis();
      renderScopedInsights();
    }

    function applyFilters(state) {
      const q = (state.searchInput.value || "").trim().toLowerCase();
      let visible = 0;
      state.bodyRows.forEach((row) => {
        const matchesText = !q || row.innerText.toLowerCase().includes(q);
        let matchesDepartment = true;
        if (state.deptColIdx !== null) {
          const dept = (row.children[state.deptColIdx]?.innerText || "").trim();
          matchesDepartment = inScopeDepartment(dept);
        }

        const show = matchesText && matchesDepartment;
        row.style.display = show ? "" : "none";
        if (show) {
          visible += 1;
        }
      });
      state.visibleEl.textContent = String(visible);
    }

    function applyAllFilters() {
      tableStates.forEach((state) => applyFilters(state));
      refreshScopedSummaries();
    }

    function captureSummaryTargets() {
      const primaryKpiGrid = document.querySelector(".kpi-grid:not(.kpi-grid-secondary)");
      if (primaryKpiGrid) {
        Array.from(primaryKpiGrid.querySelectorAll(".kpi")).forEach((card) => {
          const label = (card.querySelector(".kpi-label")?.innerText || "").trim().toLowerCase();
          const valueEl = card.querySelector(".kpi-value");
          const subEl = card.querySelector(".kpi-sub");
          if (!valueEl || !subEl) {
            return;
          }
          if (label.includes("license adoption")) {
            kpiState.license = { valueEl, subEl };
          }
          if (label.includes("employees with no tools")) {
            kpiState.noTools = { valueEl, subEl };
          }
        });
      }

      insightState.grid = document.querySelector(".insight-grid");
    }

    function addDepartmentExclusionControls() {
      const values = Array.from(departmentValues).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
      if (!values.length) {
        return;
      }

      const host = document.querySelector("main.content");
      if (!host) {
        return;
      }

      const controls = document.createElement("div");
      controls.className = "dashboard-filters";
      controls.innerHTML =
        '<div class="dashboard-filter-label">Table scope</div>' +
        '<div class="dept-filter-mode" role="radiogroup" aria-label="Department scope mode">' +
        '<label class="dept-mode-option"><input type="radio" name="dept-scope-mode" value="exclude" checked />Exclude selected</label>' +
        '<label class="dept-mode-option"><input type="radio" name="dept-scope-mode" value="include" />Include only selected</label>' +
        "</div>" +
        '<details class="dept-filter">' +
        '<summary><span class="dept-filter-title">Departments</span> <span class="dept-filter-count" aria-live="polite">All in scope</span></summary>' +
        '<div class="dept-filter-menu"></div>' +
        "</details>" +
        '<button type="button" class="dept-filter-clear">Reset</button>';

      const menu = controls.querySelector(".dept-filter-menu");
      const countEl = controls.querySelector(".dept-filter-count");
      const clearButton = controls.querySelector(".dept-filter-clear");
      const modeInputs = Array.from(controls.querySelectorAll('input[name="dept-scope-mode"]'));

      const updateCount = () => {
        const n = excludedDepartments.size;
        if (!n) {
          countEl.textContent = "All in scope";
          return;
        }
        const modeText = departmentMode === "include" ? "included" : "excluded";
        countEl.textContent = `${n} ${modeText}`;
      };

      modeInputs.forEach((input) => {
        input.addEventListener("change", () => {
          if (!input.checked) {
            return;
          }
          departmentMode = input.value === "include" ? "include" : "exclude";
          updateCount();
          applyAllFilters();
        });
      });

      values.forEach((dept) => {
        const id = `exclude-dept-${slugify(dept)}`;
        const row = document.createElement("label");
        row.className = "dept-filter-row";
        row.innerHTML = `<input type="checkbox" id="${id}" value="${dept}" /> <span>${dept}</span>`;
        const checkbox = row.querySelector("input");
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) {
            excludedDepartments.add(dept);
          } else {
            excludedDepartments.delete(dept);
          }
          updateCount();
          applyAllFilters();
        });
        menu.appendChild(row);
      });

      clearButton.addEventListener("click", () => {
        excludedDepartments.clear();
        menu.querySelectorAll('input[type="checkbox"]').forEach((input) => {
          input.checked = false;
        });
        modeInputs.forEach((input) => {
          input.checked = input.value === "exclude";
        });
        departmentMode = "exclude";
        updateCount();
        applyAllFilters();
      });

      const titleBlock = document.getElementById("title-block-header");
      const sectionNav = document.querySelector(".section-nav");
      const anchor = sectionNav || titleBlock;
      if (anchor && anchor.parentElement) {
        anchor.parentElement.insertBefore(controls, anchor.nextSibling);
      } else {
        host.insertBefore(controls, host.firstChild);
      }
      updateCount();
    }

    tables.forEach((table) => {
      if (table.dataset.enhanced === "1") {
        return;
      }
      table.dataset.enhanced = "1";

      const wrapper = document.createElement("div");
      wrapper.className = "table-shell";
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);

      const controls = document.createElement("div");
      controls.className = "table-controls";
      controls.innerHTML =
        '<label class="table-search">' +
        '<span>Filter rows</span>' +
        '<input type="search" placeholder="Type to filter..." />' +
        '</label>' +
        '<div class="table-meta">Visible rows: <strong class="table-visible">0</strong></div>';
      wrapper.insertBefore(controls, table);

      const searchInput = controls.querySelector("input");
      const visibleEl = controls.querySelector(".table-visible");
      const bodyRows = Array.from(table.querySelectorAll("tbody tr"));

      const headers = Array.from(table.querySelectorAll("thead th"));
      const deptColIdx = isDepartmentTable(headers) ? departmentColumnIndex(headers) : null;
      const headIdx = headers.findIndex((h) => /headcount/i.test((h.innerText || "").trim()));
      const withLicIdx = headers.findIndex((h) => /with\s*license/i.test((h.innerText || "").trim()));
      if (deptColIdx !== null) {
        bodyRows.forEach((row) => {
          const dept = (row.children[deptColIdx]?.innerText || "").trim();
          if (dept) {
            departmentValues.add(dept);
          }
        });
      }

      const state = {
        table,
        searchInput,
        visibleEl,
        bodyRows,
        deptColIdx,
        metrics: (deptColIdx !== null && headIdx >= 0 && withLicIdx >= 0)
          ? { headIdx, withLicIdx }
          : null,
      };
      tableStates.push(state);

      const updateVisible = () => applyFilters(state);
      searchInput.addEventListener("input", updateVisible);
      updateVisible();

      headers.forEach((th, idx) => {
        th.classList.add("sortable");
        th.setAttribute("role", "button");
        th.tabIndex = 0;
        th.dataset.sortDir = "none";

        const toggleSort = () => {
          const next = th.dataset.sortDir === "asc" ? "desc" : "asc";
          headers.forEach((h) => {
            h.dataset.sortDir = "none";
            h.classList.remove("sorted-asc", "sorted-desc");
          });
          th.dataset.sortDir = next;
          th.classList.add(next === "asc" ? "sorted-asc" : "sorted-desc");
          sortTableByColumn(table, idx, next === "asc");
          updateVisible();
        };

        th.addEventListener("click", toggleSort);
        th.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            toggleSort();
          }
        });
      });
    });

    captureSummaryTargets();
    parseDepartmentStats();
    addDepartmentExclusionControls();
    refreshScopedSummaries();
  }

  function addBackToTop() {
    const btn = document.createElement("button");
    btn.className = "back-to-top";
    btn.type = "button";
    btn.textContent = "Top";
    document.body.appendChild(btn);

    btn.addEventListener("click", () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    const onScroll = () => {
      const y = window.scrollY || document.documentElement.scrollTop;
      btn.classList.toggle("visible", y > 500);
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const headings = ensureHeadingIds();
    buildSectionNavigator(headings);
    addTableEnhancements();
    addBackToTop();
  });
})();
