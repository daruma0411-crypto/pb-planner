// ─── PB企画プランナー フロントエンド ─────────────────────────────

// ─── 状態管理 ──────────────────────────────────────────────────
let sessionId = null;
let sending = false;
let pbCard = {
  asone_part_no: null,
  price: null,
  jan_code: null,
  maker_part_no: null,
  quantity: null,
  catchcopy: null,
  spec_diff: null,
};
let completedFrameworks = [];

// セッションID生成
function generateSessionId() {
  return 'pb_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}
if (!sessionId) sessionId = generateSessionId();

// ─── ユーティリティ ────────────────────────────────────────────
function escHtml(str) {
  var d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function scrollBottom() {
  var el = document.getElementById('chat-messages');
  if (el) el.scrollTop = el.scrollHeight;
}

function adjustHeight() {
  var ta = document.getElementById('chat-input');
  if (!ta) return;
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
}

function setSending(on) {
  sending = on;
  var btn = document.getElementById('btn-send');
  if (btn) btn.disabled = on;
  var input = document.getElementById('chat-input');
  if (input) input.disabled = on;
}

function fillExample(text) {
  var input = document.getElementById('chat-input');
  if (input) {
    input.value = text;
    adjustHeight();
    sendMessage();
  }
}

// ─── マークダウン簡易変換 ─────────────────────────────────────
function simpleMarkdown(text) {
  if (!text) return '';
  // エスケープ
  var s = escHtml(text);
  // 太字
  s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // コード
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  // リスト
  s = s.replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>');
  s = s.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // 番号リスト
  s = s.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
  // 見出し
  s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  s = s.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  // 段落
  s = s.replace(/\n\n/g, '</p><p>');
  s = s.replace(/\n/g, '<br>');
  // ダウンロードリンク検出
  s = s.replace(/\/api\/download\/([^\s<"]+)/g, '<a class="download-link" href="/api/download/$1" target="_blank">📥 ダウンロード: $1</a>');
  return '<p>' + s + '</p>';
}

// ─── チャットメッセージ表示 ───────────────────────────────────
function clearWelcome() {
  var welcome = document.querySelector('.welcome-message');
  if (welcome) welcome.remove();
}

function appendUserBubble(text) {
  clearWelcome();
  var container = document.getElementById('chat-messages');
  var msg = document.createElement('div');
  msg.className = 'msg user';
  msg.innerHTML =
    '<div class="msg-bubble">' + escHtml(text) + '</div>' +
    '<div class="msg-avatar">👤</div>';
  container.appendChild(msg);
  scrollBottom();
}

function appendAIBubble(html) {
  clearWelcome();
  var container = document.getElementById('chat-messages');
  var msg = document.createElement('div');
  msg.className = 'msg ai';
  msg.innerHTML =
    '<div class="msg-avatar">🤖</div>' +
    '<div class="msg-bubble">' + html + '</div>';
  container.appendChild(msg);
  scrollBottom();
  return msg;
}

function appendTyping() {
  clearWelcome();
  var container = document.getElementById('chat-messages');
  var msg = document.createElement('div');
  msg.className = 'msg ai';
  msg.id = 'typing-msg';
  msg.innerHTML =
    '<div class="msg-avatar">🤖</div>' +
    '<div class="msg-bubble">' +
    '<div class="typing-indicator">' +
    '<span class="typing-dot"></span>' +
    '<span class="typing-dot"></span>' +
    '<span class="typing-dot"></span>' +
    '</div></div>';
  container.appendChild(msg);
  scrollBottom();
  return msg;
}

function removeTyping() {
  var el = document.getElementById('typing-msg');
  if (el) el.remove();
}

// ─── PBカード更新 ─────────────────────────────────────────────
function updatePbCard(card) {
  if (!card) return;
  pbCard = card;
  var fields = ['asone_part_no', 'price', 'jan_code', 'maker_part_no',
                'quantity', 'catchcopy', 'spec_diff'];
  var filled = 0;

  fields.forEach(function(f) {
    var el = document.getElementById('pb-' + f);
    if (!el) return;
    var val = card[f];
    if (val) {
      el.textContent = val;
      el.className = 'pb-value confirmed';
      filled++;
    } else {
      el.textContent = '—';
      el.className = 'pb-value';
    }
  });

  // プログレスバッジ更新
  var badge = document.getElementById('pb-progress');
  if (badge) {
    badge.textContent = filled + '/7';
    if (filled === 7) {
      badge.className = 'progress-badge complete';
    } else {
      badge.className = 'progress-badge';
    }
  }
}

// ─── フレームワークバッジ更新 ─────────────────────────────────
function updateFrameworkBadges(frameworks) {
  if (!frameworks) return;
  completedFrameworks = frameworks;
  var badges = document.querySelectorAll('.fw-badge');
  badges.forEach(function(badge) {
    var fw = badge.getAttribute('data-framework');
    if (frameworks.indexOf(fw) >= 0) {
      badge.classList.add('done');
    } else {
      badge.classList.remove('done');
    }
  });
}

// ─── API通信 ──────────────────────────────────────────────────
function sendMessage() {
  if (sending) return;
  var input = document.getElementById('chat-input');
  var text = (input.value || '').trim();
  if (!text) return;

  input.value = '';
  adjustHeight();
  appendUserBubble(text);
  setSending(true);
  appendTyping();

  fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: text,
      session_id: sessionId,
    }),
  })
  .then(function(resp) {
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
  })
  .then(function(data) {
    removeTyping();
    setSending(false);

    // AIの返答表示
    if (data.reply) {
      appendAIBubble(simpleMarkdown(data.reply));
    }

    // セッションID同期
    if (data.session_id) sessionId = data.session_id;

    // PBカード更新
    if (data.pb_card) updatePbCard(data.pb_card);

    // フレームワーク更新
    if (data.framework_results) updateFrameworkBadges(data.framework_results);
  })
  .catch(function(err) {
    removeTyping();
    setSending(false);
    appendAIBubble('<p style="color:var(--c-accent)">通信エラーが発生しました: ' + escHtml(err.message) + '</p>');
  });
}

// ─── フレームワーク分析リクエスト ─────────────────────────────
function requestAnalysis(framework) {
  var names = {
    '3c': '3C分析',
    'swot': 'SWOT分析',
    'positioning': 'ポジショニングマップ分析',
    '5forces': '5Forces分析',
    'price_map': '価格帯マップ分析',
  };
  var input = document.getElementById('chat-input');
  if (input) {
    input.value = (names[framework] || framework) + 'を実施してください';
    sendMessage();
  }
}

// ─── アウトプット生成リクエスト ───────────────────────────────
function requestOutput(type) {
  var messages = {
    'pim_excel': 'PIMデータのExcelを生成してください',
    'translate': 'PIMデータを英訳してExcelを生成してください',
    'catalog_html': 'カタログHTMLを生成してください',
    'proposal_word': '企画書のWordファイルを生成してください',
  };
  var input = document.getElementById('chat-input');
  if (input) {
    input.value = messages[type] || type;
    sendMessage();
  }
}

// ─── リセット ─────────────────────────────────────────────────
function resetAll() {
  if (!confirm('PB企画カードと会話履歴をリセットしますか？')) return;

  fetch('/api/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  }).catch(function() {});

  // ローカル状態リセット
  sessionId = generateSessionId();
  pbCard = {
    asone_part_no: null, price: null, jan_code: null,
    maker_part_no: null, quantity: null, catchcopy: null, spec_diff: null,
  };
  completedFrameworks = [];

  // UI リセット
  updatePbCard(pbCard);
  updateFrameworkBadges([]);

  var container = document.getElementById('chat-messages');
  container.innerHTML =
    '<div class="welcome-message">' +
    '<div class="welcome-icon">🏭</div>' +
    '<h2>PB企画を始めましょう</h2>' +
    '<p>仕入れ先の製品を選んで、PB化の企画をAIと一緒に進められます。</p>' +
    '<div class="quick-start">' +
    '<button class="quick-btn" onclick="fillExample(\'トミー精工のオートクレーブでPB企画したい\')">🔬 トミー精工 オートクレーブ</button>' +
    '<button class="quick-btn" onclick="fillExample(\'メディカル用途のオートクレーブを探して\')">🏥 メディカル用オートクレーブ</button>' +
    '<button class="quick-btn" onclick="fillExample(\'ラボ用の大容量オートクレーブを検索\')">🧪 ラボ用 大容量</button>' +
    '</div></div>';
}

// ─── モバイルダッシュボード ───────────────────────────────────
function toggleMobileDashboard() {
  var panel = document.getElementById('dashboard');
  if (panel) panel.classList.toggle('open');
}

// ─── イベントリスナー ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  // 送信ボタン
  var btnSend = document.getElementById('btn-send');
  if (btnSend) btnSend.addEventListener('click', sendMessage);

  // Enter キー送信
  var chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    chatInput.addEventListener('input', adjustHeight);
  }

  // リセットボタン
  var btnReset = document.getElementById('btn-reset-all');
  if (btnReset) btnReset.addEventListener('click', resetAll);

  // ダッシュボード外クリックで閉じる（モバイル）
  document.addEventListener('click', function(e) {
    var panel = document.getElementById('dashboard');
    var toggle = document.getElementById('mobile-toggle');
    if (panel && panel.classList.contains('open') &&
        !panel.contains(e.target) && e.target !== toggle) {
      panel.classList.remove('open');
    }
  });
});
