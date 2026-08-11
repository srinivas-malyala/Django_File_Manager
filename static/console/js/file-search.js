(() => {
  "use strict";

  const container = document.querySelector("[data-live-search]");
  const input = document.querySelector("#id_search");
  if (!container || !input) {
    return;
  }

  const results = container.querySelector("[data-live-search-results]");
  const status = container.querySelector("[data-live-search-status]");
  let debounceTimer;

  const clearResults = () => {
    results.replaceChildren();
    results.classList.add("d-none");
    status.textContent = "";
  };

  const renderResults = (items) => {
    results.replaceChildren();
    items.forEach((item) => {
      const row = document.createElement("li");
      row.className = "list-group-item";
      const link = document.createElement("a");
      link.href = item.detail_url;
      link.textContent = item.original_filename;
      row.appendChild(link);
      results.appendChild(row);
    });
    results.classList.toggle("d-none", items.length === 0);
    status.textContent = `${items.length} live result${items.length === 1 ? "" : "s"}`;
  };

  const search = async () => {
    const query = input.value.trim();
    if (!query) {
      clearResults();
      return;
    }

    const url = new URL(container.dataset.searchUrl, window.location.origin);
    url.searchParams.set("search", query);
    url.searchParams.set("page_size", "10");
    status.textContent = "Searching…";
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error("Search request failed");
      }
      const payload = await response.json();
      renderResults(payload.data.results);
    } catch (_error) {
      clearResults();
      status.textContent = "Live search is temporarily unavailable.";
    }
  };

  input.addEventListener("input", () => {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(search, 300);
  });
})();
