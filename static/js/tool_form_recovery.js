(() => {
  const pendingForms = new Set();

  function restore(form, reset = false) {
    const button = form.querySelector('[data-processing-label]');
    if (button) {
      button.innerHTML = button.dataset.processingLabel;
      button.disabled = false;
      delete button.dataset.processingLabel;
    }
    if (reset) {
      form.reset();
      form.querySelectorAll('.file-summary').forEach(summary => {
        summary.textContent = 'No files selected';
      });
      form.querySelectorAll('.drop-zone.has-file').forEach(zone => {
        zone.classList.remove('has-file');
      });
    }
    pendingForms.delete(form);
  }

  document.addEventListener('submit', event => {
    if (event.defaultPrevented || event.target.method?.toLowerCase() !== 'post') return;
    const form = event.target;
    const button = form.querySelector('button[type="submit"], button:not([type])');
    if (button && !button.dataset.processingLabel) {
      button.dataset.processingLabel = button.innerHTML;
      button.textContent = 'Processing…';
      button.disabled = true;
    }
    form.dataset.submittedAt = String(Date.now());
    pendingForms.add(form);

    // File downloads do not navigate away, so return the form to a fresh state.
    window.setTimeout(() => {
      if (pendingForms.has(form)) restore(form, true);
    }, 3000);
  });

  window.addEventListener('pageshow', () => {
    document.querySelectorAll('form').forEach(form => restore(form));
  });

  window.addEventListener('focus', () => {
    pendingForms.forEach(form => {
      if (Date.now() - Number(form.dataset.submittedAt || 0) > 1000) restore(form, true);
    });
  });
})();
