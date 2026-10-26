/* Màn hình quay số: kết quả do SERVER chọn (secrets.SystemRandom); trình duyệt chỉ chạy hiệu ứng.
   Hiệu ứng, pháo giấy, toàn màn hình lấy từ web quay số gốc. Màn hình chỉ hiện MÃ, không hiện họ tên. */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const base = `/api/admin/lucky-draw/${window.LUCKY.eventId}`;
  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Chỉ dùng cho hiệu ứng trang trí (vị trí pháo giấy, câu chúc), không quyết định ai trúng
  function randInt(n) {
    const buf = new Uint32Array(1);
    crypto.getRandomValues(buf);
    return buf[0] % n;
  }

  let state = null;
  let drawing = false;      // đang chạy hiệu ứng / đang gọi server
  let pending = [];         // kết quả đã quay, chờ Lưu hoặc Quay lại: [{id, patron_code}]
  let decoys = [];

  // ---------- Gọi API ----------
  async function api(method, path, body) {
    const options = { method, headers: {} };
    if (body !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
    const response = await fetch(base + path, options);
    const data = await response.json().catch(() => ({ success: false, message: 'Phản hồi không hợp lệ từ máy chủ.' }));
    if (response.status === 401) { location.href = '/admin/login?next=' + encodeURIComponent(location.pathname); }
    return data;
  }

  async function loadState() {
    const data = await api('GET', '?screen=1');
    if (!data.success) { showMsg(data.message || 'Không tải được dữ liệu quay số.'); return false; }
    state = data;
    pending = data.pending.map((w) => ({ id: w.id, patron_code: w.patron_code, prize_id: w.prize_id }));
    $('stage').style.setProperty('--stage-bg', `url("${data.hinh_nen_url}")`);
    return true;
  }

  // ---------- Hiển thị ----------
  function showMsg(text, kind) {
    const box = $('msg');
    box.replaceChildren();
    if (!text) return;
    const div = document.createElement('div');
    div.className = 'msg ' + (kind || 'error');
    div.textContent = text;
    box.append(div);
  }

  const CHEERS = [
    'Quá đỉnh! May mắn đã gọi tên bạn! 🍀',
    'Thư viện gửi tặng bạn một tràng pháo tay! 👏',
    'Hôm nay là ngày may mắn của bạn! ⭐',
    'Chúc mừng! Sách hay luôn đồng hành cùng bạn! 📚',
    'Wow! Xin chúc mừng người may mắn! 🥳'
  ];
  function cheer() {
    const box = $('msg');
    box.replaceChildren();
    const div = document.createElement('div');
    div.className = 'cheer';
    div.textContent = CHEERS[randInt(CHEERS.length)];
    box.append(div);
  }

  function buildSlots(n) {
    const wrap = $('slots');
    wrap.replaceChildren();
    wrap.dataset.n = n >= 10 ? 'many' : String(n);
    const els = [];
    for (let i = 0; i < n; i++) {
      const slot = document.createElement('div'); slot.className = 'slot';
      const name = document.createElement('div'); name.className = 'slot-name';
      slot.append(name); wrap.append(slot);
      els.push({ root: slot, name });
    }
    return els;
  }

  function currentPrize() {
    if (!state) return null;
    return state.prizes.find((p) => String(p.id) === $('prizeSelect').value) || null;
  }

  // Quay được khi giải còn suất và còn người trong danh sách quay
  function canDraw(prize) {
    return !!prize && prize.con_lai > 0 && prize.nguoi_con_lai > 0;
  }

  function renderIdle() {
    const els = buildSlots(1);
    els[0].root.classList.add('idle');
    const prize = currentPrize();
    els[0].name.textContent = !state || !state.tong_nguoi ? 'Chưa có người check-in'
      : !state.prizes.length ? 'Chưa có giải thưởng'
      : state.prizes.every((p) => p.con_lai === 0) ? 'Đã quay đủ tất cả giải'
      : (prize && prize.con_lai === 0) ? 'Giải này đã quay đủ' : 'Sẵn sàng quay';
  }

  function renderPending() {
    const els = buildSlots(pending.length);
    pending.forEach((w, i) => { els[i].root.classList.add('done'); els[i].name.textContent = w.patron_code; });
  }

  function renderControls() {
    const select = $('prizeSelect');
    const keep = select.value;
    select.replaceChildren();
    state.prizes.forEach((p) => {
      const option = document.createElement('option');
      option.value = String(p.id);
      option.textContent = `${p.ten_giai} (${p.da_quay}/${p.so_luong})${p.con_lai === 0 ? ' – đủ' : ''}`;
      option.disabled = p.con_lai === 0;
      select.append(option);
    });
    const stillOk = state.prizes.some((p) => String(p.id) === keep && p.con_lai > 0);
    const firstOpen = state.prizes.find((p) => p.con_lai > 0);
    select.value = stillOk ? keep : (firstOpen ? String(firstOpen.id) : (state.prizes[0] ? String(state.prizes[0].id) : ''));
    refreshPrizeInfo();
  }

  function refreshPrizeInfo() {
    const prize = currentPrize();
    $('stagePrize').replaceChildren(document.createTextNode(prize ? prize.ten_giai : 'Quay số trúng thưởng'));
    if (prize) {
      const small = document.createElement('small');
      small.textContent = `Còn ${prize.con_lai} suất`;
      $('stagePrize').append(small);
    }
    $('poolText').textContent = prize ? `Còn ${prize.nguoi_con_lai} người trong danh sách quay` : '';
    updateLock();
  }

  function updateLock() {
    const busy = drawing || pending.length > 0;
    const prize = currentPrize();
    $('btnDraw').disabled = busy || !canDraw(prize);
    $('prizeSelect').disabled = busy;
    
    $('confirmBox').classList.toggle('hidden', !(pending.length && !drawing));
    $('btnResults').disabled = drawing;
  }

  // ---------- Hiệu ứng chạy mã ----------
  function animate(picks, done) {
    const k = picks.length;
    const reduced = reducedMotion();
    const dur = reduced ? 600 : 5000;
    const stagger = reduced ? 80 : (k > 1 ? Math.min(700, 2500 / (k - 1)) : 0);
    const els = buildSlots(k);
    const t0 = performance.now();
    const pool = decoys.length ? decoys : picks.map((p) => p.patron_code);
    const slots = els.map((e, i) => {
      e.root.classList.add('spinning');
      return { e, stop: t0 + dur - (k - 1 - i) * stagger, next: t0, done: false, code: picks[i].patron_code };
    });
    function frame(now) {
      let waiting = 0;
      for (const s of slots) {
        if (s.done) continue;
        if (now >= s.stop) {
          s.e.name.textContent = s.code;
          s.e.root.classList.remove('spinning');
          s.e.root.classList.add('done');
          s.done = true;
          continue;
        }
        waiting++;
        if (now >= s.next) {
          s.e.name.textContent = pool[randInt(pool.length)];
          const p = Math.min(1, (now - t0) / (s.stop - t0));
          s.next = now + 45 + 520 * p * p * p;
        }
      }
      if (waiting) requestAnimationFrame(frame); else done();
    }
    requestAnimationFrame(frame);
  }

  // ---------- Pháo giấy ----------
  function confetti() {
    if (reducedMotion()) return;
    const cv = $('confetti');
    const stage = $('stage');
    cv.width = stage.clientWidth; cv.height = stage.clientHeight;
    const ctx = cv.getContext('2d');
    const colors = ['#f6b800', '#2e9a5f', '#4fc3f7', '#7be495', '#ffffff', '#1976b8'];
    const icons = ['📖', '⭐', '❤️', '📚', '✨'];
    const sprites = icons.map((ic) => {
      const c = document.createElement('canvas'); c.width = c.height = 40;
      const x = c.getContext('2d'); x.font = '30px sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(ic, 20, 22);
      return c;
    });
    const parts = [];
    const W = cv.width, H = cv.height;
    const burst = (x, y, n, dirX) => {
      for (let i = 0; i < n; i++) {
        parts.push({
          x, y,
          vx: dirX * (3 + randInt(1100) / 100) + (dirX ? 0 : (randInt(2000) - 1000) / 100),
          vy: -(randInt(1400) / 100) - 6,
          s: 6 + randInt(8), c: colors[randInt(colors.length)], r: randInt(360),
          icon: randInt(100) < 22 ? sprites[randInt(sprites.length)] : null
        });
      }
    };
    burst(W / 2, H * 0.45, 60, 0);
    burst(0, H * 0.9, 50, 1);
    burst(W, H * 0.9, 50, -1);
    const DUR = 3200;
    const t0 = performance.now();
    (function tick(now) {
      const age = now - t0;
      ctx.clearRect(0, 0, cv.width, cv.height);
      if (age > DUR) return;
      parts.forEach((p) => {
        p.vy += 0.27; p.vx *= 0.995; p.x += p.vx; p.y += p.vy; p.r += 6;
        ctx.save();
        ctx.translate(p.x, p.y); ctx.rotate(p.r * Math.PI / 180);
        ctx.globalAlpha = Math.max(0, 1 - age / DUR);
        if (p.icon) { const z = p.s * 2.4; ctx.drawImage(p.icon, -z / 2, -z / 2, z, z); }
        else { ctx.fillStyle = p.c; ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); }
        ctx.restore();
      });
      requestAnimationFrame(tick);
    })(t0);
  }

  // ---------- QUAY / Lưu / Quay lại ----------
  async function startDraw() {
    if (drawing || pending.length) return;
    const prize = currentPrize();
    if (!prize) { showMsg('Chưa có giải thưởng. Hãy thêm giải ở trang thiết lập.'); return; }
    drawing = true;
    updateLock();
    showMsg('');
    const data = await api('POST', '/draw', { prize_id: prize.id });
    if (!data.success) {
      drawing = false;
      showMsg(data.message || 'Không quay được.');
      await loadState();   // đồng bộ lại (vd. tab khác vừa quay hoặc vừa lưu)
      renderControls();
      if (pending.length) renderPending(); else renderIdle();
      updateLock();
      return;
    }
    pending = data.winners.map((w) => ({ id: w.id, patron_code: w.patron_code, prize_id: prize.id }));
    decoys = data.decoys || [];
    $('stage').classList.remove('celebrate');
    $('stage').classList.add('drawing');
    animate(pending, () => {
      drawing = false;
      $('stage').classList.remove('drawing');
      $('stage').classList.add('celebrate');
      updateLock();
      confetti();
      cheer();
      $('btnSave').focus();
    });
  }

  async function saveResult() {
    if (!pending.length || drawing) return;
    drawing = true; updateLock();
    const data = await api('POST', '/confirm');
    drawing = false;
    $('stage').classList.remove('celebrate');
    if (!data.success) showMsg(data.message || 'Không lưu được.');
    else showMsg(data.message, 'info');
    await loadState();
    renderControls();
    renderIdle();
    updateLock();
  }

  async function discardResult() {
    $('redoModal').classList.add('hidden');
    if (!pending.length || drawing) return;
    drawing = true; updateLock();
    const data = await api('POST', '/reject');
    drawing = false;
    $('stage').classList.remove('celebrate');
    showMsg(data.success ? '' : (data.message || 'Không bỏ được kết quả.'));
    await loadState();
    renderControls();
    renderIdle();
    updateLock();
  }

  // ---------- Toàn màn hình ----------
  function isFull() { return document.fullscreenElement === $('stage') || $('stage').classList.contains('pseudo-full'); }
  function updateFullBtn() { $('btnFull').textContent = isFull() ? 'Thoát toàn màn hình' : 'Toàn màn hình'; }
  function toggleFull() {
    const st = $('stage');
    if (isFull()) {
      if (document.fullscreenElement) document.exitFullscreen();
      st.classList.remove('pseudo-full');
      updateFullBtn();
      return;
    }
    if (st.requestFullscreen) st.requestFullscreen().catch(() => { st.classList.add('pseudo-full'); updateFullBtn(); });
    else { st.classList.add('pseudo-full'); updateFullBtn(); }
  }
  document.addEventListener('fullscreenchange', updateFullBtn);

  // ---------- Màn hình kết quả ----------
  let resultsEnteredFull = false;
  async function openResults() {
    await loadState();    // luôn lấy kết quả mới nhất từ server
    const body = $('rvBody');
    body.replaceChildren();
    let any = false;
    state.prizes.forEach((prize) => {
      const winners = state.winners.filter((w) => w.prize_id === prize.id);
      if (!winners.length) return;
      any = true;
      const card = document.createElement('div'); card.className = 'rv-card';
      const title = document.createElement('h3'); title.textContent = `${prize.ten_giai} (${winners.length}/${prize.so_luong})`;
      card.append(title);
      winners.forEach((w) => {
        const line = document.createElement('div'); line.className = 'rv-code'; line.textContent = w.patron_code;
        card.append(line);
      });
      body.append(card);
    });
    if (!any) {
      const empty = document.createElement('div'); empty.className = 'rv-empty';
      empty.textContent = 'Chưa có giải nào được quay.';
      body.append(empty);
    }
    $('resultsView').classList.remove('hidden');
    if (!isFull()) { resultsEnteredFull = true; toggleFull(); }
    $('btnResultsClose').focus();
  }
  function closeResults() {
    $('resultsView').classList.add('hidden');
    if (resultsEnteredFull && isFull()) toggleFull();
    resultsEnteredFull = false;
  }
  const resultsOpen = () => !$('resultsView').classList.contains('hidden');

  // ---------- Sự kiện ----------
  $('btnDraw').addEventListener('click', startDraw);
  $('btnSave').addEventListener('click', saveResult);
  $('btnRedo').addEventListener('click', () => {
    if (!pending.length || drawing) return;
    $('redoModal').classList.remove('hidden');
    $('btnRedoNo').focus();
  });
  $('btnRedoNo').addEventListener('click', () => { $('redoModal').classList.add('hidden'); $('btnSave').focus(); });
  $('btnRedoYes').addEventListener('click', discardResult);
  $('btnFull').addEventListener('click', toggleFull);
  $('btnResults').addEventListener('click', openResults);
  $('btnResultsClose').addEventListener('click', closeResults);
  $('prizeSelect').addEventListener('change', refreshPrizeInfo);

  function typing(t) {
    if (!t || !t.tagName) return false;
    const tag = t.tagName.toLowerCase();
    if (tag === 'textarea' || tag === 'select') return true;
    if (tag === 'input') return !/^(checkbox|radio|file|button)$/i.test(t.type);
    return false;
  }
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Escape' && resultsOpen()) { closeResults(); return; }
    if (e.code === 'Escape' && !$('redoModal').classList.contains('hidden')) { $('redoModal').classList.add('hidden'); return; }
    if (e.code === 'Escape' && $('stage').classList.contains('pseudo-full')) { toggleFull(); return; }
    if (e.code !== 'Space' || typing(e.target)) return;
    e.preventDefault();
    if (!e.repeat && !drawing && !pending.length && !resultsOpen()) startDraw();
  });
  document.addEventListener('keyup', (e) => { if (e.code === 'Space' && !typing(e.target)) e.preventDefault(); });

  // ---------- Khởi động ----------
  (async function init() {
    if (!(await loadState())) return;
    renderControls();
    if (pending.length) {
      // Tải lại trang khi còn kết quả chờ: hiện lại để Lưu / Quay lại
      const prize = state.prizes.find((p) => p.id === pending[0].prize_id);
      if (prize) $('prizeSelect').value = String(prize.id);
      refreshPrizeInfo();
      renderPending();
      showMsg('Đang có kết quả chờ Lưu hoặc Quay lại.', 'info');
    } else {
      renderIdle();
    }
    updateLock();
  })();
})();
