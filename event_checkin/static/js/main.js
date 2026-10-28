/* Hộp xác nhận dùng chung: thay confirm() của trình duyệt, cùng giao diện với mọi hộp thoại khác.
   Dùng:  if (!await confirmAsync('Nội dung...')) return;   (trong hàm async). Trả về true/false như confirm().
   Dòng đầu của nội dung là câu hỏi, các dòng sau là ghi chú. Tên nút "đồng ý" suy ra từ câu hỏi. */
window.confirmAsync = function (message, options) {
  const text = String(message || '');
  const lines = text.split('\n').map((line) => line.trim()).filter(Boolean);
  const first = lines[0] || '';
  const guess = [
    [/^Xóa/, 'Xóa', true],
    [/^(Hủy|Huỷ)/, 'Hủy kết quả', true],
    [/^Lọc trùng/, 'Lọc trùng', false],
    [/^Nhập/, 'Nhập', false],
    [/^Sẽ gửi/, 'Gửi', false],
    [/^Ẩn/, 'Ẩn', false],
    [/^Khôi phục/, 'Khôi phục', false],
    [/^Vị trí/, 'Lưu và áp dụng', false],
  ].find(([pattern]) => pattern.test(first));
  const opts = Object.assign(
    { title: 'Xác nhận', okText: guess ? guess[1] : 'Đồng ý', danger: guess ? guess[2] : false },
    options || {},
  );
  opts.cancelText = opts.cancelText || (opts.danger ? 'Giữ lại' : 'Hủy');

  if (typeof HTMLDialogElement === 'undefined') {
    return Promise.resolve(window.confirm(text));
  }
  return new Promise((resolve) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'app-dialog';
    const body = document.createElement('div');
    body.className = 'app-dialog__body';
    const title = document.createElement('h2');
    title.className = 'app-dialog__title';
    title.textContent = opts.title;
    body.append(title);
    lines.forEach((line) => {
      const p = document.createElement('p');
      p.className = 'app-dialog__text';
      p.textContent = line;
      body.append(p);
    });
    const actions = document.createElement('div');
    actions.className = 'app-dialog__actions';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'btn btn--ghost';
    cancel.textContent = opts.cancelText;
    const ok = document.createElement('button');
    ok.type = 'button';
    ok.className = 'btn ' + (opts.danger ? 'btn--danger-solid' : 'btn--primary');
    ok.textContent = opts.okText;
    actions.append(cancel, ok);
    body.append(actions);
    dialog.append(body);
    document.body.append(dialog);

    let result = false;
    cancel.addEventListener('click', () => dialog.close());
    ok.addEventListener('click', () => { result = true; dialog.close(); });
    dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });  // bấm ra ngoài = hủy
    dialog.addEventListener('close', () => { dialog.remove(); resolve(result); });
    dialog.showModal();
    (opts.danger ? cancel : ok).focus();
  });
};

window.appUtils = {
  formatDateTimeVN(dateTimeString) {
    if (!dateTimeString) return '';
    const date = new Date(dateTimeString);
    if (Number.isNaN(date.getTime())) return dateTimeString;
    const pad = (n) => String(n).padStart(2, '0');
    // chuẩn hiển thị: dd/mm/yyyy hh:mm
    return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  },

  // Thẻ sự kiện/card admin mờ dần + trượt lên khi cuộn tới (thay vì chạy ngay
  // lúc tải trang) -- gọi lại hàm này sau khi thêm HTML mới vào DOM (ví dụ
  // "Xem thêm" hoặc kết quả tìm kiếm) để quan sát luôn các thẻ vừa chèn.
  observeReveal(root) {
    const scope = root || document;
    const targets = scope.querySelectorAll('.event-card:not(.is-revealed), .admin-event-card:not(.is-revealed)');
    if (!targets.length) return;

    if (!('IntersectionObserver' in window)) {
      targets.forEach((el) => el.classList.add('is-revealed'));
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-revealed');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    targets.forEach((el) => observer.observe(el));
  },
};

document.addEventListener('DOMContentLoaded', () => window.appUtils.observeReveal());

// Header: đổ bóng khi cuộn trang + menu dạng hamburger trên mobile.
(function () {
  const header = document.getElementById('siteHeader');
  const SCROLL_THRESHOLD = 12;

  function updateHeaderOnScroll() {
    if (!header) return;
    header.classList.toggle('is-scrolled', window.scrollY > SCROLL_THRESHOLD);
  }
  window.addEventListener('scroll', updateHeaderOnScroll, { passive: true });
  updateHeaderOnScroll();

  const navToggle = document.getElementById('navToggle');
  const primaryNav = document.getElementById('primaryNav');
  const navOverlay = document.getElementById('navOverlay');
  if (!navToggle || !primaryNav || !navOverlay) return;

  function openMobileNav() {
    primaryNav.classList.add('is-open');
    navOverlay.classList.add('is-visible');
    navToggle.setAttribute('aria-expanded', 'true');
    navToggle.setAttribute('aria-label', 'Đóng menu điều hướng');
    document.body.style.overflow = 'hidden';
  }
  function closeMobileNav() {
    primaryNav.classList.remove('is-open');
    navOverlay.classList.remove('is-visible');
    navToggle.setAttribute('aria-expanded', 'false');
    navToggle.setAttribute('aria-label', 'Mở menu điều hướng');
    document.body.style.overflow = '';
  }

  navToggle.addEventListener('click', () => {
    const isOpen = navToggle.getAttribute('aria-expanded') === 'true';
    if (isOpen) closeMobileNav(); else openMobileNav();
  });
  navOverlay.addEventListener('click', closeMobileNav);
  primaryNav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', closeMobileNav);
  });
  // Mở "Quản lý đơn vị" từ menu điện thoại: đóng menu để nó không phủ lên hộp thoại (làm không bấm được nút ⋯)
  primaryNav.querySelectorAll('[data-open-don-vi]').forEach((item) => {
    item.addEventListener('click', closeMobileNav);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMobileNav();
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 960) closeMobileNav();  // cùng điểm gãy 960px với CSS
  });
})();

document.addEventListener('DOMContentLoaded', () => {
  const settings = document.querySelector('.admin-settings');
  if (!settings) return;

  const button = settings.querySelector('.admin-settings__button');
  const menu = settings.querySelector('.admin-settings__menu');
  const logoutButton = document.querySelector('[data-admin-logout]');
  const openDonVi = settings.querySelector('[data-open-don-vi]');
  const donViModal = document.getElementById('donViModal');
  const donViForm = document.getElementById('donViForm');
  const donViId = document.getElementById('donViId');
  const donViName = document.getElementById('donViName');
  const donViActive = document.getElementById('donViActive');
  const donViMessage = document.getElementById('donViMessage');
  const donViList = document.getElementById('donViList');
  const resetDonViForm = document.getElementById('resetDonViForm');
  const donViBulkToolbar = document.getElementById('donViBulkToolbar');
  const donViBulkCount = document.getElementById('donViBulkCount');
  const donViBulkHide = document.getElementById('donViBulkHide');
  const donViBulkDelete = document.getElementById('donViBulkDelete');
  const donViBulkCancel = document.getElementById('donViBulkCancel');

  let donViItems = [];
  let bulkMode = false;
  let selectedIds = new Set();
  let openRowMenu = null;

  function closeMenu() {
    menu.hidden = true;
    button.setAttribute('aria-expanded', 'false');
  }

  function closeRowMenu() {
    if (!openRowMenu) return;
    openRowMenu.menu.hidden = true;
    openRowMenu.toggleButton.setAttribute('aria-expanded', 'false');
    openRowMenu = null;
  }

  button.addEventListener('click', (event) => {
    event.stopPropagation();
    const shouldOpen = menu.hidden;
    menu.hidden = !shouldOpen;
    button.setAttribute('aria-expanded', String(shouldOpen));
  });

  if (logoutButton) {
    logoutButton.addEventListener('click', async () => {
      logoutButton.disabled = true;
      try {
        await fetch('/api/admin/logout', {
          method: 'POST',
          credentials: 'same-origin',
          cache: 'no-store',
        });
      } finally {
        window.location.replace('/admin/login');
      }
    });
  }

  document.addEventListener('click', (event) => {
    if (!settings.contains(event.target)) {
      closeMenu();
    }
    if (openRowMenu && !openRowMenu.toggleButton.parentElement.contains(event.target)) {
      closeRowMenu();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeMenu();
      closeRowMenu();
      closeDonViModal();
    }
  });

  function showDonViMessage(text, type = 'success') {
    donViMessage.hidden = false;
    donViMessage.className = `message message--${type}`;
    donViMessage.textContent = text;
  }

  function resetForm() {
    donViId.value = '';
    donViName.value = '';
    donViActive.checked = true;
    donViName.focus();
  }

  function openDonViModal() {
    donViModal.classList.add('is-open');
    donViModal.setAttribute('aria-hidden', 'false');
    donViMessage.hidden = true;
    bulkMode = false;
    selectedIds.clear();
    closeMenu();
    loadDonVi();
    window.setTimeout(() => donViName.focus(), 0);
  }

  function closeDonViModal() {
    if (!donViModal) return;
    donViModal.classList.remove('is-open');
    donViModal.setAttribute('aria-hidden', 'true');
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.message || 'Không thể xử lý yêu cầu.');
    }
    return data;
  }

  function renderDonVi(items) {
    donViItems = items;
    closeRowMenu();

    if (!items.length) {
      donViList.innerHTML = '<p class="muted">Chưa có đơn vị nào.</p>';
      donViBulkToolbar.hidden = true;
      return;
    }

    if (bulkMode) {
      donViList.innerHTML = items.map((item) => `
        <div class="admin-data-item admin-data-item--bulk" data-id="${item.id}">
          <label class="admin-data-item__check">
            <input type="checkbox" data-bulk-checkbox ${selectedIds.has(item.id) ? 'checked' : ''}>
          </label>
          <div>
            <strong>${escapeHtml(item.ten_don_vi)}</strong>
            <span>${item.is_active ? 'Đang sử dụng' : 'Đã ẩn'}</span>
          </div>
        </div>
      `).join('');
      bindBulkCheckboxes();
      updateBulkToolbar();
      return;
    }

    donViBulkToolbar.hidden = true;
    donViList.innerHTML = items.map((item) => `
      <div class="admin-data-item" data-id="${item.id}">
        <div>
          <strong>${escapeHtml(item.ten_don_vi)}</strong>
          <span>${item.is_active ? 'Đang sử dụng' : 'Đã ẩn'}</span>
        </div>
        <div class="admin-data-actions admin-data-menu-wrap">
          <button class="btn btn--ghost btn--sm" type="button" data-menu-toggle aria-haspopup="true" aria-expanded="false">⋯</button>
          <div class="admin-data-menu" hidden>
            <button class="admin-settings__item" type="button" data-menu-edit>Sửa</button>
            <button class="admin-settings__item" type="button" data-menu-toggle-active>${item.is_active ? 'Ẩn' : 'Hiện'}</button>
            <button class="admin-settings__item" type="button" data-menu-delete>Xóa</button>
            <button class="admin-settings__item" type="button" data-menu-bulk>Chọn nhiều</button>
          </div>
        </div>
      </div>
    `).join('');
    bindRowMenus();
  }

  function bindRowMenus() {
    donViList.querySelectorAll('[data-menu-toggle]').forEach((toggleButton) => {
      const rowMenu = toggleButton.nextElementSibling;
      toggleButton.addEventListener('click', (event) => {
        event.stopPropagation();
        const isOpen = !rowMenu.hidden;
        closeRowMenu();
        if (!isOpen) {
          // Định vị theo viewport (fixed) thay vì absolute trong item, để menu
          // không bị cắt bởi #donViList (khung danh sách có overflow-y cố định).
          const rect = toggleButton.getBoundingClientRect();
          rowMenu.style.position = 'fixed';
          rowMenu.style.top = `${rect.bottom + 6}px`;
          rowMenu.style.left = 'auto';
          rowMenu.style.right = `${window.innerWidth - rect.right}px`;
          rowMenu.hidden = false;
          toggleButton.setAttribute('aria-expanded', 'true');
          openRowMenu = { menu: rowMenu, toggleButton };
        }
      });
    });

    function findItem(button) {
      const row = button.closest('.admin-data-item');
      return donViItems.find((entry) => String(entry.id) === row.dataset.id);
    }

    donViList.querySelectorAll('[data-menu-edit]').forEach((menuButton) => {
      menuButton.addEventListener('click', () => {
        const item = findItem(menuButton);
        closeRowMenu();
        if (!item) return;
        donViId.value = item.id;
        donViName.value = item.ten_don_vi;
        donViActive.checked = item.is_active;
        donViName.focus();
      });
    });

    donViList.querySelectorAll('[data-menu-toggle-active]').forEach((menuButton) => {
      menuButton.addEventListener('click', async () => {
        const item = findItem(menuButton);
        closeRowMenu();
        if (!item) return;
        const willActivate = !item.is_active;
        const confirmText = willActivate ? 'Khôi phục đơn vị này?' : 'Ẩn đơn vị này?';
        if (!await confirmAsync(confirmText)) return;
        try {
          await requestJson(`/api/admin/don-vi/${item.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ ten_don_vi: item.ten_don_vi, is_active: willActivate }),
          });
          showDonViMessage(willActivate ? 'Đã khôi phục đơn vị.' : 'Đã ẩn đơn vị.');
          loadDonVi();
        } catch (error) {
          showDonViMessage(error.message, 'error');
        }
      });
    });

    donViList.querySelectorAll('[data-menu-delete]').forEach((menuButton) => {
      menuButton.addEventListener('click', async () => {
        const item = findItem(menuButton);
        closeRowMenu();
        if (!item) return;
        if (!await confirmAsync(`Xóa vĩnh viễn đơn vị "${item.ten_don_vi}"? Hành động này không thể hoàn tác.`)) return;
        try {
          await requestJson(`/api/admin/don-vi/${item.id}`, { method: 'DELETE' });
          showDonViMessage('Đã xóa đơn vị.');
          loadDonVi();
        } catch (error) {
          showDonViMessage(error.message, 'error');
        }
      });
    });

    donViList.querySelectorAll('[data-menu-bulk]').forEach((menuButton) => {
      menuButton.addEventListener('click', () => {
        closeRowMenu();
        bulkMode = true;
        selectedIds.clear();
        renderDonVi(donViItems);
      });
    });
  }

  function bindBulkCheckboxes() {
    donViList.querySelectorAll('[data-bulk-checkbox]').forEach((checkbox) => {
      checkbox.addEventListener('change', () => {
        const row = checkbox.closest('.admin-data-item');
        const id = Number(row.dataset.id);
        if (checkbox.checked) selectedIds.add(id); else selectedIds.delete(id);
        updateBulkToolbar();
      });
    });
  }

  function updateBulkToolbar() {
    donViBulkToolbar.hidden = false;
    donViBulkCount.textContent = `Đã chọn ${selectedIds.size} đơn vị`;
    const hasSelection = selectedIds.size > 0;
    donViBulkHide.disabled = !hasSelection;
    donViBulkDelete.disabled = !hasSelection;
  }

  function exitBulkMode() {
    bulkMode = false;
    selectedIds.clear();
    renderDonVi(donViItems);
  }

  async function loadDonVi() {
    try {
      const data = await requestJson('/api/admin/don-vi');
      renderDonVi(data.data || []);
    } catch (error) {
      showDonViMessage(error.message, 'error');
    }
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  if (openDonVi && donViModal) {
    openDonVi.addEventListener('click', openDonViModal);
  }

  document.querySelectorAll('[data-close-don-vi]').forEach((item) => {
    item.addEventListener('click', closeDonViModal);
  });

  if (resetDonViForm) {
    resetDonViForm.addEventListener('click', resetForm);
  }

  if (donViBulkCancel) {
    donViBulkCancel.addEventListener('click', exitBulkMode);
  }

  if (donViBulkHide) {
    donViBulkHide.addEventListener('click', async () => {
      if (!selectedIds.size) return;
      if (!await confirmAsync(`Ẩn ${selectedIds.size} đơn vị đã chọn?`)) return;
      try {
        await requestJson('/api/admin/don-vi/an-hang-loat', {
          method: 'POST',
          body: JSON.stringify({ ids: Array.from(selectedIds) }),
        });
        showDonViMessage('Đã ẩn các đơn vị đã chọn.');
        exitBulkMode();
        loadDonVi();
      } catch (error) {
        showDonViMessage(error.message, 'error');
      }
    });
  }

  if (donViBulkDelete) {
    donViBulkDelete.addEventListener('click', async () => {
      if (!selectedIds.size) return;
      if (!await confirmAsync(`Xóa vĩnh viễn ${selectedIds.size} đơn vị đã chọn? Hành động này không thể hoàn tác.`)) return;
      try {
        const result = await requestJson('/api/admin/don-vi/xoa-hang-loat', {
          method: 'POST',
          body: JSON.stringify({ ids: Array.from(selectedIds) }),
        });
        const { da_xoa, loi } = result.data;
        if (loi.length) {
          const chiTiet = loi.map((entry) => `${entry.ten_don_vi}: ${entry.ly_do}`).join('; ');
          showDonViMessage(`Đã xóa ${da_xoa.length} đơn vị. Không xóa được ${loi.length} đơn vị — ${chiTiet}`, 'error');
        } else {
          showDonViMessage(`Đã xóa ${da_xoa.length} đơn vị.`);
        }
        exitBulkMode();
        loadDonVi();
      } catch (error) {
        showDonViMessage(error.message, 'error');
      }
    });
  }

  if (donViForm) {
    donViForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const id = donViId.value;
      const payload = {
        ten_don_vi: donViName.value.trim(),
        is_active: donViActive.checked,
      };
      try {
        await requestJson(id ? `/api/admin/don-vi/${id}` : '/api/admin/don-vi', {
          method: id ? 'PUT' : 'POST',
          body: JSON.stringify(payload),
        });
        showDonViMessage(id ? 'Đã cập nhật đơn vị.' : 'Đã thêm đơn vị.');
        resetForm();
        loadDonVi();
      } catch (error) {
        showDonViMessage(error.message, 'error');
      }
    });
  }
});
