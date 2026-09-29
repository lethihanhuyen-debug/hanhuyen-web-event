(function () {
  "use strict";

  // Không gắn chatbot vào trang quản trị / check-in để không ảnh hưởng thao tác vận hành.
  var path = window.location.pathname;
  if (/^\/(admin|checkin)(\/|$)/.test(path)) return;

  var MAX_LEN = 300;
  var STORAGE_KEY = "evchat_history_v1";
  var history = [];
  var pending = false;

  function store(op, value) {
    try {
      if (op === "get") return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch (e) { return []; }
    return [];
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function init() {
    var toggle = el("button", "evchat-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-label", "Mở trợ lý hỏi đáp sự kiện");
    toggle.innerHTML =
      '<svg class="evchat-toggle__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M12 3c.4 3.6 2.4 5.6 6 6-3.6.4-5.6 2.4-6 6-.4-3.6-2.4-5.6-6-6 3.6-.4 5.6-2.4 6-6z"/>' +
      '<path d="M19 15c.2 1.6 1 2.4 2.5 2.5-1.5.2-2.3 1-2.5 2.5-.2-1.5-1-2.3-2.5-2.5 1.5-.1 2.3-.9 2.5-2.5z"/>' +
      "</svg>" +
      '<span class="evchat-toggle__label">Hỏi sự kiện</span>';

    var panel = el("div", "evchat-panel");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Trợ lý sự kiện");

    var header = el("div", "evchat-header");
    header.appendChild(el("span", null, "Trợ lý sự kiện"));
    var closeBtn = el("button", "evchat-close", "×");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Đóng");
    header.appendChild(closeBtn);

    var messages = el("div", "evchat-messages");
    messages.setAttribute("aria-live", "polite");

    var form = el("form", "evchat-form");
    var input = el("textarea", "evchat-input");
    input.rows = 1;
    input.maxLength = MAX_LEN;
    input.placeholder = "Hỏi về sự kiện...";
    input.setAttribute("aria-label", "Câu hỏi của bạn");
    var send = el("button", "evchat-send", "Gửi");
    send.type = "submit";
    form.appendChild(input);
    form.appendChild(send);

    panel.appendChild(header);
    panel.appendChild(messages);
    panel.appendChild(form);
    document.body.appendChild(toggle);
    document.body.appendChild(panel);

    function scrollDown() { messages.scrollTop = messages.scrollHeight; }

    function addMessage(role, text, isError) {
      var cls = "evchat-msg " + (role === "user" ? "user" : "bot") + (isError ? " error" : "");
      var node = el("div", cls, text);
      messages.appendChild(node);
      scrollDown();
      return node;
    }

    function addCards(events) {
      if (!events || !events.length) return;
      var wrap = el("div", "evchat-cards");
      events.forEach(function (ev) {
        var card = el("div", "evchat-card");
        if (ev.image_url && /^\/[^/]/.test(ev.image_url)) {
          var img = document.createElement("img");
          img.src = ev.image_url;
          img.alt = "";
          img.loading = "lazy";
          card.appendChild(img);
        }
        var body = el("div", "evchat-card-body");
        body.appendChild(el("div", "evchat-card-title", ev.title || ""));
        body.appendChild(el("div", null, "📅 " + (ev.date || "") + (ev.time ? " · 🕐 " + ev.time : "")));
        body.appendChild(el("div", null, "📍 " + (ev.location || "")));
        if (ev.capacity) body.appendChild(el("div", null, "👥 " + ev.capacity));
        body.appendChild(el("div", null, ev.status || ""));

        // Chỉ dựng liên kết nội bộ (bắt đầu bằng một dấu "/"), không nhận URL ngoài.
        if (ev.url && /^\/[^\/\\]/.test(ev.url)) {
          var actions = el("div", "evchat-card-actions");
          var detail = el("a", "evchat-btn ghost", "Xem chi tiết");
          detail.href = ev.url;
          actions.appendChild(detail);
          if (ev.can_register) {
            var reg = el("a", "evchat-btn", "Đăng ký");
            reg.href = ev.url;
            actions.appendChild(reg);
          }
          body.appendChild(actions);
        }
        card.appendChild(body);
        wrap.appendChild(card);
      });
      messages.appendChild(wrap);
      scrollDown();
    }

    function persist() { store("set", history.slice(-12)); }

    function setOpen(open) {
      panel.classList.toggle("is-open", open);
      if (open) { input.focus(); scrollDown(); }
    }

    toggle.addEventListener("click", function () { setOpen(!panel.classList.contains("is-open")); });
    closeBtn.addEventListener("click", function () { setOpen(false); toggle.focus(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && panel.classList.contains("is-open")) setOpen(false);
    });

    // Thu gọn nút thành hình tròn khi cuộn xuống (đỡ che nội dung), mở rộng
    // lại khi cuộn lên hoặc về gần đầu trang. Rê chuột/focus khi đang thu gọn
    // cũng hiện lại chữ tạm thời.
    var COLLAPSE_AFTER = 120;
    var lastScrollY = window.scrollY;
    var scrollTicking = false;
    function onScroll() {
      var y = window.scrollY;
      if (y < COLLAPSE_AFTER || y < lastScrollY - 8) toggle.classList.remove("is-collapsed");
      else if (y > lastScrollY + 8) toggle.classList.add("is-collapsed");
      lastScrollY = y;
      scrollTicking = false;
    }
    window.addEventListener("scroll", function () {
      if (!scrollTicking) { requestAnimationFrame(onScroll); scrollTicking = true; }
    }, { passive: true });

    var wasCollapsedBeforePeek = false;
    function peek() { wasCollapsedBeforePeek = toggle.classList.contains("is-collapsed"); toggle.classList.remove("is-collapsed"); }
    function unpeek() { if (wasCollapsedBeforePeek && window.scrollY >= COLLAPSE_AFTER) toggle.classList.add("is-collapsed"); }
    toggle.addEventListener("mouseenter", peek);
    toggle.addEventListener("mouseleave", unpeek);
    toggle.addEventListener("focus", peek);
    toggle.addEventListener("blur", unpeek);

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
      }
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (pending) return;
      var text = input.value.trim();
      if (!text) return;

      addMessage("user", text);
      input.value = "";
      pending = true;
      send.disabled = true;

      var typing = el("div", "evchat-msg bot");
      var dots = el("span", "evchat-typing");
      dots.appendChild(document.createElement("span"));
      dots.appendChild(document.createElement("span"));
      dots.appendChild(document.createElement("span"));
      typing.appendChild(dots);
      messages.appendChild(typing);
      scrollDown();

      fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: history.slice(-6) })
      })
        .then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (data) {
            return { ok: res.ok, data: data };
          });
        })
        .then(function (r) {
          typing.remove();
          var reply = (r.data && typeof r.data.message === "string" && r.data.message) ||
            "Xin lỗi, hiện chatbot đang tạm thời không thể trả lời. Vui lòng thử lại sau.";
          var okReply = r.ok && r.data && r.data.success !== false;
          addMessage("bot", reply, !okReply);
          if (okReply) {
            addCards(r.data.events);
            history.push({ role: "user", text: text });
            history.push({ role: "bot", text: reply.slice(0, MAX_LEN) });
            persist();
          }
        })
        .catch(function () {
          typing.remove();
          addMessage("bot", "Không kết nối được máy chủ. Vui lòng thử lại sau.", true);
        })
        .then(function () {
          pending = false;
          send.disabled = false;
          input.focus();
        });
    });

    history = (store("get") || []).filter(function (t) { return t && (t.role === "user" || t.role === "bot"); });
    if (history.length) {
      history.forEach(function (t) { addMessage(t.role === "user" ? "user" : "bot", t.text); });
    } else {
      addMessage("bot", "Xin chào! Mình có thể giúp bạn tìm sự kiện, xem thời gian, địa điểm và tình trạng đăng ký. Bạn muốn hỏi gì nào?");
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
