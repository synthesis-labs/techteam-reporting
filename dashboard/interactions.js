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

      const updateVisible = () => {
        const q = (searchInput.value || "").trim().toLowerCase();
        let visible = 0;
        bodyRows.forEach((row) => {
          const hit = !q || row.innerText.toLowerCase().includes(q);
          row.style.display = hit ? "" : "none";
          if (hit) {
            visible += 1;
          }
        });
        visibleEl.textContent = String(visible);
      };

      searchInput.addEventListener("input", updateVisible);
      updateVisible();

      const headers = Array.from(table.querySelectorAll("thead th"));
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
