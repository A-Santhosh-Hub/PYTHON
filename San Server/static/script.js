(() => {
  const selectAll = document.getElementById("selectAll");
  const checks = Array.from(document.querySelectorAll(".item-check"));
  const actionBar = document.getElementById("actionBar");
  const selCount = document.getElementById("selCount");
  const selSize = document.getElementById("selSize");
  const filterBox = document.getElementById("filterBox");
  const rows = Array.from(document.querySelectorAll(".row"));

  function humanSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    const units = ["KB", "MB", "GB", "TB"];
    let val = bytes / 1024, i = 0;
    while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
    return val.toFixed(val < 10 ? 2 : 1) + " " + units[i];
  }

  function updateSelectionSummary() {
    const checked = checks.filter((c) => c.checked);
    if (checked.length === 0) {
      actionBar.hidden = true;
      return;
    }
    actionBar.hidden = false;
    selCount.textContent = checked.length;

    let knownBytes = 0;
    let folderCount = 0;
    checked.forEach((c) => {
      if (c.dataset.kind === "file") knownBytes += Number(c.dataset.size || 0);
      else folderCount += 1;
    });

    let text = knownBytes > 0 ? humanSize(knownBytes) : "";
    if (folderCount > 0) {
      text += (text ? " + " : "") + folderCount + " folder" + (folderCount > 1 ? "s" : "") + " (size shown once it starts)";
    }
    selSize.textContent = text;
  }

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      checks.forEach((c) => {
        // only toggle checkboxes currently visible (respects the active filter)
        const row = c.closest(".row");
        if (!row.hasAttribute("data-hidden")) c.checked = selectAll.checked;
      });
      updateSelectionSummary();
    });
  }

  checks.forEach((c) => c.addEventListener("change", updateSelectionSummary));

  if (filterBox) {
    filterBox.addEventListener("input", () => {
      const q = filterBox.value.trim().toLowerCase();
      rows.forEach((row) => {
        const match = !q || row.dataset.name.includes(q);
        row.style.display = match ? "" : "none";
        if (match) row.removeAttribute("data-hidden");
        else row.setAttribute("data-hidden", "1");
      });
    });
  }

  updateSelectionSummary();
})();
