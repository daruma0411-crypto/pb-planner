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

function scrollToLatest() {
  var el = document.getElementById('chat-messages');
  if (el) el.scrollTop = 0;
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
  // 箇条書き(•/-/*)で「項目名: 値」パターン → 番号付きに強制変換
  var specNum = 1;
  s = s.replace(/^[•\-\*]\s+(.+?[:：]\s*.+)$/gm, function(match, p1) {
    return (specNum++) + '. ' + p1;
  });
  // 太字
  s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // コード
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  // 残りの箇条書き（項目:値パターン以外）
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
  // ダウンロードURL参照をテキストから除去（download_urlsハンドラで表示するため）
  s = s.replace(/\[?[^\]]*\]?\(?\/api\/download\/[^\s<")\]]+\)?/g, '');
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
  container.prepend(msg);
  scrollToLatest();
}

function appendAIBubble(html) {
  clearWelcome();
  var container = document.getElementById('chat-messages');
  var msg = document.createElement('div');
  msg.className = 'msg ai';
  msg.innerHTML =
    '<div class="msg-avatar">🤖</div>' +
    '<div class="msg-bubble">' + html + '</div>';
  container.prepend(msg);
  scrollToLatest();
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
  container.prepend(msg);
  scrollToLatest();
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
      // spec_diffは長いので省略表示
      if (f === 'spec_diff' && val.length > 20) {
        var changeCount = (val.match(/\uff0f/g) || []).length + 1; // ／で区切り
        el.textContent = '\u25cf\u6e08 (' + changeCount + '\u4ef6)';
        el.title = val; // ホバーで全文表示
      } else {
        el.textContent = val;
      }
      el.className = 'pb-value confirmed';
      filled++;
    } else {
      el.textContent = '\u2014';
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

    // AIの返答 + スペック連番 + DLリンクを同じバブルに結合表示
    var replyHtml = '';
    if (data.reply) {
      replyHtml += simpleMarkdown(data.reply);
    }
    // サーバー生成のスペック連番テキストを追加（AIフォーマットに依存しない）
    if (data.spec_numbered) {
      replyHtml += '<div class="spec-numbered"><h4>仕様諸元</h4><ol>';
      data.spec_numbered.split('\n').forEach(function(line) {
        var m = line.match(/^\d+\.\s+(.+)$/);
        if (m) replyHtml += '<li>' + escHtml(m[1]) + '</li>';
      });
      replyHtml += '</ol></div>';
    }
    if (data.download_urls && data.download_urls.length > 0) {
      replyHtml += '<div class="download-links">';
      data.download_urls.forEach(function(item) {
        replyHtml += '<a class="download-link" href="' + escHtml(item.download_url) + '" target="_blank">' +
                  '\uD83D\uDCE5 ' + escHtml(item.filename) + '</a>';
      });
      replyHtml += '</div>';
    }
    if (replyHtml) {
      appendAIBubble(replyHtml);
    }

    // セッションID同期
    if (data.session_id) sessionId = data.session_id;

    // PBカード更新
    if (data.pb_card) updatePbCard(data.pb_card);

    // フレームワーク更新
    if (data.framework_results) updateFrameworkBadges(data.framework_results);

    // フレームワークビジュアル表示
    if (data.framework_visuals && data.framework_visuals.length > 0) {
      data.framework_visuals.forEach(function(vis) {
        renderFrameworkVisual(vis);
      });
    }
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

// ─── フレームワークビジュアル描画 ─────────────────────────────

function renderFrameworkVisual(vis) {
  if (!vis || !vis.type) return;
  switch (vis.type) {
    case '3c': render3cGrid(vis.data); break;
    case 'swot': renderSwotGrid(vis.data); break;
    case 'positioning': renderScatterChart(vis.data); break;
    case '5forces': renderForcesChart(vis.data); break;
    case 'price_map': renderPriceBar(vis.data); break;
  }
}

function render3cGrid(data) {
  var sections = [
    {key: 'customer', label: '👥 Customer（顧客）', cls: 'c3-customer'},
    {key: 'competitor', label: '⚔️ Competitor（競合）', cls: 'c3-competitor'},
    {key: 'company', label: '🏢 Company（自社）', cls: 'c3-company'},
  ];
  var html = '<div class="c3-grid">';
  sections.forEach(function(s) {
    html += '<div class="c3-cell ' + s.cls + '">';
    html += '<div class="c3-label">' + s.label + '</div>';
    html += '<ul>';
    (data[s.key] || []).forEach(function(item) {
      html += '<li>' + escHtml(item) + '</li>';
    });
    html += '</ul></div>';
  });
  html += '</div>';
  appendAIBubble(html);
}

function renderSwotGrid(data) {
  var html = '<div class="swot-grid">';
  var quadrants = [
    {key: 'strengths', label: 'S 強み', cls: 'swot-s'},
    {key: 'weaknesses', label: 'W 弱み', cls: 'swot-w'},
    {key: 'opportunities', label: 'O 機会', cls: 'swot-o'},
    {key: 'threats', label: 'T 脅威', cls: 'swot-t'},
  ];
  quadrants.forEach(function(q) {
    html += '<div class="swot-cell ' + q.cls + '">';
    html += '<div class="swot-label">' + q.label + '</div>';
    html += '<ul>';
    (data[q.key] || []).forEach(function(item) {
      html += '<li>' + escHtml(item) + '</li>';
    });
    html += '</ul></div>';
  });
  html += '</div>';
  appendAIBubble(html);
}

function renderScatterChart(data) {
  var container = document.createElement('div');
  container.className = 'chart-container';
  var canvas = document.createElement('canvas');
  container.appendChild(canvas);

  var msg = appendAIBubble('');
  var bubble = msg.querySelector('.msg-bubble');
  bubble.appendChild(container);

  var chartDatasets = data.datasets.map(function(ds) {
    return {
      label: ds.label,
      data: ds.data,
      backgroundColor: ds.backgroundColor,
      borderColor: ds.borderColor,
      pointRadius: ds.pointRadius || 6,
      pointHoverRadius: 8,
    };
  });

  // ベース製品を★で強調
  if (data.base_product) {
    chartDatasets.push({
      label: '\u2605 ' + (data.base_model || 'ベース製品'),
      data: [data.base_product],
      backgroundColor: 'rgba(230, 0, 18, 0.9)',
      borderColor: '#E60012',
      pointRadius: 10,
      pointStyle: 'star',
      pointHoverRadius: 14,
    });
  }

  // データ範囲を計算してスケールを最適化
  var allX = [], allY = [];
  chartDatasets.forEach(function(ds) {
    ds.data.forEach(function(pt) { allX.push(pt.x); allY.push(pt.y); });
  });
  var xMin = Math.min.apply(null, allX), xMax = Math.max.apply(null, allX);
  var yMin = Math.min.apply(null, allY), yMax = Math.max.apply(null, allY);
  var xPad = Math.max((xMax - xMin) * 0.1, 5);
  var yPad = Math.max((yMax - yMin) * 0.1, 5);

  new Chart(canvas, {
    type: 'scatter',
    data: { datasets: chartDatasets },
    options: {
      responsive: true,
      aspectRatio: 1.4,
      plugins: {
        title: { display: true, text: '\u30DD\u30B8\u30B7\u30E7\u30CB\u30F3\u30B0: ' + data.axis_x + ' \u00D7 ' + data.axis_y, font: {size: 14} },
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              var dsIdx = ctx.datasetIndex;
              var ds = data.datasets[dsIdx];
              var model = ds && ds.models ? ds.models[ctx.dataIndex] : '';
              return (model || ctx.dataset.label) + ' (' + ctx.parsed.x + ', ' + ctx.parsed.y + ')';
            }
          }
        }
      },
      scales: {
        x: { title: { display: true, text: data.axis_x }, min: Math.max(0, xMin - xPad), max: xMax + xPad },
        y: { title: { display: true, text: data.axis_y }, min: Math.max(0, yMin - yPad), max: yMax + yPad },
      }
    }
  });
  scrollToLatest();
}

function renderForcesChart(data) {
  function dots(score) {
    var s = '';
    for (var i = 0; i < 5; i++) s += i < score ? '\u25CF' : '\u25CB';
    return s;
  }
  function scoreColor(score) {
    if (score >= 4) return '#F44336';
    if (score >= 3) return '#FF9800';
    return '#4CAF50';
  }

  var html = '<div class="forces-grid">';
  var ne = data.new_entrants;
  html += '<div class="force-box force-top">';
  html += '<div class="force-label">' + escHtml(ne.label) + '</div>';
  html += '<div class="force-dots" style="color:' + scoreColor(ne.score) + '">' + dots(ne.score) + '</div>';
  html += '<div class="force-detail">' + escHtml(ne.detail) + '</div></div>';

  var sp = data.supplier_power;
  html += '<div class="force-box force-left">';
  html += '<div class="force-label">' + escHtml(sp.label) + '</div>';
  html += '<div class="force-dots" style="color:' + scoreColor(sp.score) + '">' + dots(sp.score) + '</div>';
  html += '<div class="force-detail">' + escHtml(sp.detail) + '</div></div>';

  var ri = data.rivalry;
  html += '<div class="force-box force-center">';
  html += '<div class="force-label">' + escHtml(ri.label) + '</div>';
  html += '<div class="force-dots" style="color:' + scoreColor(ri.score) + '">' + dots(ri.score) + '</div>';
  html += '<div class="force-detail">' + escHtml(ri.detail) + '</div></div>';

  var bp = data.buyer_power;
  html += '<div class="force-box force-right">';
  html += '<div class="force-label">' + escHtml(bp.label) + '</div>';
  html += '<div class="force-dots" style="color:' + scoreColor(bp.score) + '">' + dots(bp.score) + '</div>';
  html += '<div class="force-detail">' + escHtml(bp.detail) + '</div></div>';

  var su = data.substitutes;
  html += '<div class="force-box force-bottom">';
  html += '<div class="force-label">' + escHtml(su.label) + '</div>';
  html += '<div class="force-dots" style="color:' + scoreColor(su.score) + '">' + dots(su.score) + '</div>';
  html += '<div class="force-detail">' + escHtml(su.detail) + '</div></div>';

  html += '</div>';
  appendAIBubble(html);
}

function renderPriceBar(data) {
  var container = document.createElement('div');
  container.className = 'chart-container';
  // 製品数に応じた高さ（1製品あたり40px + 余白80px）
  var barCount = (data.labels || []).length;
  var chartHeight = Math.max(200, barCount * 40 + 80);
  container.style.height = chartHeight + 'px';
  var canvas = document.createElement('canvas');
  container.appendChild(canvas);

  var msg = appendAIBubble('');
  var bubble = msg.querySelector('.msg-bubble');
  bubble.appendChild(container);

  var plugins = [];
  // バーの右端に価格ラベルを表示
  plugins.push({
    id: 'barValueLabels',
    afterDatasetsDraw: function(chart) {
      var ctx = chart.ctx;
      ctx.save();
      ctx.font = '11px sans-serif';
      ctx.fillStyle = '#333';
      ctx.textBaseline = 'middle';
      chart.data.datasets[0].data.forEach(function(val, i) {
        var meta = chart.getDatasetMeta(0);
        var bar = meta.data[i];
        var label = val >= 1000000 ? '\u00A5' + (val/10000).toFixed(0) + '\u4E07' : '\u00A5' + val.toLocaleString();
        ctx.fillText(label, bar.x + 6, bar.y);
      });
      ctx.restore();
    }
  });
  if (data.base_price) {
    plugins.push({
      id: 'basePriceLine',
      afterDraw: function(chart) {
        var xScale = chart.scales.x;
        var ctx = chart.ctx;
        var x = xScale.getPixelForValue(data.base_price);
        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([5, 5]);
        ctx.moveTo(x, chart.chartArea.top);
        ctx.lineTo(x, chart.chartArea.bottom);
        ctx.strokeStyle = '#E60012';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.fillStyle = '#E60012';
        ctx.font = '12px sans-serif';
        ctx.fillText('\u25BC ' + data.base_model, x + 4, chart.chartArea.top + 14);
        ctx.restore();
      }
    });
  }

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [{
        label: '\u4FA1\u683C (\u5186)',
        data: data.values,
        backgroundColor: data.colors,
        borderColor: data.borders,
        borderWidth: 1,
        barThickness: 24,
        maxBarThickness: 32,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      layout: {
        padding: { right: 20 }
      },
      plugins: {
        title: { display: true, text: '\u4FA1\u683C\u5E2F\u30DE\u30C3\u30D7', font: {size: 14, weight: 'bold'}, padding: {bottom: 12} },
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              return '\u00A5' + ctx.parsed.x.toLocaleString();
            }
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: '\u4FA1\u683C (\u5186)', font: {size: 12} },
          ticks: {
            font: { size: 11 },
            callback: function(val) {
              if (val >= 1000000) return '\u00A5' + (val / 10000).toFixed(0) + '\u4E07';
              return '\u00A5' + val.toLocaleString();
            },
            maxTicksLimit: 6,
          },
          grid: { color: 'rgba(0,0,0,0.05)' },
        },
        y: {
          ticks: { font: { size: 12 }, padding: 4 },
          grid: { display: false },
        }
      }
    },
    plugins: plugins,
  });
  scrollToLatest();
}
