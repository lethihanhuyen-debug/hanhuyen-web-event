window.appUtils = {
  formatDateTimeVN(dateTimeString) {
    if (!dateTimeString) return '';
    const date = new Date(dateTimeString);
    if (Number.isNaN(date.getTime())) return dateTimeString;
    return new Intl.DateTimeFormat('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(date);
  },
};

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

  function closeMenu() {
    menu.hidden = true;
    button.setAttribute('aria-expanded', 'false');
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
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeMenu();
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
    if (!items.length) {
      donViList.innerHTML = '<p class="muted">Chưa có đơn vị nào.</p>';
      return;
    }
    donViList.innerHTML = items.map((item) => `
      <div class="admin-data-item" data-id="${item.id}">
        <div>
          <strong>${escapeHtml(item.ten_don_vi)}</strong>
          <span>${item.is_active ? 'Đang sử dụng' : 'Đã ẩn'}</span>
        </div>
        <div class="admin-data-actions">
          <button class="btn btn--ghost btn--sm" type="button" data-edit-don-vi>Sửa</button>
          <button class="btn btn--danger btn--sm" type="button" data-delete-don-vi>${item.is_active ? 'Xóa' : 'Đã xóa'}</button>
        </div>
      </div>
    `).join('');

    donViList.querySelectorAll('[data-edit-don-vi]').forEach((itemButton) => {
      itemButton.addEventListener('click', () => {
        const row = itemButton.closest('.admin-data-item');
        const item = items.find((entry) => String(entry.id) === row.dataset.id);
        if (!item) return;
        donViId.value = item.id;
        donViName.value = item.ten_don_vi;
        donViActive.checked = item.is_active;
        donViName.focus();
      });
    });

    donViList.querySelectorAll('[data-delete-don-vi]').forEach((itemButton) => {
      itemButton.addEventListener('click', async () => {
        const row = itemButton.closest('.admin-data-item');
        const item = items.find((entry) => String(entry.id) === row.dataset.id);
        if (!item || !item.is_active) return;
        if (!confirm(`Xóa đơn vị "${item.ten_don_vi}" khỏi danh sách hiển thị?`)) return;
        try {
          await requestJson(`/api/admin/don-vi/${item.id}`, { method: 'DELETE' });
          showDonViMessage('Đã xóa đơn vị khỏi danh sách hiển thị.');
          loadDonVi();
        } catch (error) {
          showDonViMessage(error.message, 'error');
        }
      });
    });
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
