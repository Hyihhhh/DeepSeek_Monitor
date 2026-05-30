/**
 * DeepSeek Platform Monitor - Frontend Logic
 */
let refreshTimer = null;
const REFRESH_INTERVAL = 60000;

const MODEL_COLORS = {
    'deepseek-v4-pro': 'v4',
    'deepseek-v4-flash': 'flash',
    'deepseek-r1': 'r1',
    'deepseek-v3': 'default-bar',
};

function modelBarClass(name) {
    for (const [key, cls] of Object.entries(MODEL_COLORS)) {
        if (name.toLowerCase().includes(key)) return cls;
    }
    return 'default-bar';
}

function fmtNum(n) {
    if (n == null) return '--';
    const num = parseInt(n);
    if (isNaN(num)) return '--';
    if (num >= 1e8) return (num / 1e8).toFixed(2) + ' 亿';
    if (num >= 1e4) return (num / 1e4).toFixed(1) + ' 万';
    return num.toLocaleString();
}

function fmtShort(n) {
    if (n == null) return '--';
    const num = parseInt(n);
    if (isNaN(num)) return '--';
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e4) return (num / 1e4).toFixed(1) + '万';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toLocaleString();
}

function fmtMoney(v) {
    if (v == null) return '¥--';
    const n = parseFloat(v);
    if (isNaN(n)) return '¥--';
    return '¥' + n.toFixed(n < 1 ? 4 : 2);
}

// ==================== API ====================

async function checkStatus() {
    try {
        const r = await fetch('/api/status');
        const d = await r.json();
        const dot = document.getElementById('statusDot');
        const txt = document.getElementById('statusText');
        if (d.logged_in) {
            dot.className = 'status-dot'; txt.textContent = '已连接';
            document.getElementById('headerUser').textContent = d.user_name || '';
            showDashboard();
        } else {
            dot.className = 'status-dot disconnected'; txt.textContent = '等待登录';
            showLogin();
        }
    } catch (e) {
        document.getElementById('statusDot').className = 'status-dot disconnected';
        document.getElementById('statusText').textContent = '服务异常';
    }
}

async function startLogin() {
    const phone = document.getElementById('phoneInput').value.trim();
    if (!phone || phone.length < 10) { showMsg('请输入正确的手机号', 'error'); return; }
    const btn = document.getElementById('loginBtn');
    btn.disabled = true; btn.textContent = '发送中'; showMsg('正在发送验证码', '');
    try {
        const r = await fetch('/api/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({phone}) });
        const d = await r.json();
        if (d.success) {
            if (d.already_logged_in) { showMsg('已登录', 'success'); setTimeout(checkStatus, 500); }
            else {
                document.getElementById('codeGroup').style.display = 'block';
                document.getElementById('loginBtn').style.display = 'none';
                document.getElementById('verifyBtn').style.display = 'block';
                showMsg('验证码已发送', 'success');
                document.getElementById('codeInput').focus();
            }
        } else { showMsg(d.message || '发送失败', 'error'); btn.disabled = false; btn.textContent = '发送验证码'; }
    } catch (e) { showMsg('网络错误', 'error'); btn.disabled = false; btn.textContent = '发送验证码'; }
}

async function verifyCode() {
    const code = document.getElementById('codeInput').value.trim();
    if (!code || code.length < 4) { showMsg('请输入验证码', 'error'); return; }
    const btn = document.getElementById('verifyBtn');
    btn.disabled = true; btn.textContent = '验证中'; showMsg('正在验证', '');
    try {
        const r = await fetch('/api/verify', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({code}) });
        const d = await r.json();
        if (d.success) { showMsg('登录成功', 'success'); setTimeout(checkStatus, 800); }
        else { showMsg(d.message || '验证失败', 'error'); btn.disabled = false; btn.textContent = '确认登录'; }
    } catch (e) { showMsg('网络错误', 'error'); btn.disabled = false; btn.textContent = '确认登录'; }
}

function showMsg(msg, type) {
    const el = document.getElementById('loginMsg');
    el.textContent = msg; el.className = 'login-msg ' + (type || '');
}

// ==================== Dashboard ====================

function showLogin() { document.getElementById('loginPanel').style.display = 'flex'; document.getElementById('dashboard').style.display = 'none'; }
function showDashboard() { document.getElementById('loginPanel').style.display = 'none'; document.getElementById('dashboard').style.display = 'block'; loadDashboard(); initAutostart(); }

async function loadDashboard() {
    try {
        const r = await fetch('/api/dashboard');
        const result = await r.json();
        if (!result.success) { if (result.need_login) showLogin(); return; }
        const data = result.data;
        renderBalance(data.balance || {}, data.cost || {}, data.usage || {});
        renderToday(data.daily || {}, data.usage || {});
        renderChart(data.daily || {});
        renderModels(data.models || []);
        document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('zh-CN');
        if (!refreshTimer) refreshTimer = setInterval(loadDashboard, REFRESH_INTERVAL);
    } catch (e) { console.error(e); }
}

// ── Balance Bar ──
let _lastAlerted = false;

function renderBalance(balance, cost, usage) {
    const total = (parseFloat(balance.normal)||0) + (parseFloat(balance.bonus)||0);
    document.getElementById('currentBalance').textContent = fmtMoney(total);
    document.getElementById('toppedUpBalance').textContent = fmtMoney(balance.normal);
    document.getElementById('bonusBalance').textContent = fmtMoney(balance.bonus);
    document.getElementById('monthlyCost').textContent = fmtMoney(cost.monthly);
    document.getElementById('tokenEstValue').textContent = fmtNum(balance.token_estimation);
    document.getElementById('balanceHitRate').textContent = (usage.cache_hit_rate || 0) + '%';

    // Balance alert
    const threshold = parseFloat(document.getElementById('alertThreshold').value) || 5;
    localStorage.setItem('alertThreshold', threshold);
    const bar = document.getElementById('balanceBar');
    const balEl = document.getElementById('currentBalance');

    if (total < threshold) {
        bar.classList.add('warning');
        balEl.classList.add('warning-low');
        if (!_lastAlerted) {
            sendNotification('DeepSeek 余额不足',
                '当前余额 ' + fmtMoney(total) + '，低于预警阈值 ' + fmtMoney(threshold) + '，请及时续费！');
            _lastAlerted = true;
        }
    } else {
        bar.classList.remove('warning');
        balEl.classList.remove('warning-low');
        _lastAlerted = false;
    }
}

function sendNotification(title, body) {
    if ('Notification' in window) {
        if (Notification.permission === 'granted') {
            new Notification(title, { body, requireInteraction: true });
        } else if (Notification.permission === 'default') {
            Notification.requestPermission().then(p => {
                if (p === 'granted') new Notification(title, { body, requireInteraction: true });
            });
        }
    }
}

// ── Today's Usage ──
function renderToday(daily, usage) {
    const today = (daily && daily.today) ? daily.today : {};
    document.getElementById('todayInput').textContent = fmtNum(today.input || 0);
    document.getElementById('todayOutput').textContent = fmtNum(today.output || 0);
    document.getElementById('todayTotal').textContent = fmtNum(today.tokens || 0);
    document.getElementById('todayCost').textContent = fmtMoney(today.cost || 0);
}

// ── 7-Day Bar Chart ──
function renderChart(daily) {
    const container = document.getElementById('barChart');
    const days = (daily && daily.seven_days) ? daily.seven_days : [];
    if (!days.length) { container.innerHTML = '<div class="loading-placeholder">暂无数据</div>'; return; }

    const maxVal = Math.max(...days.map(d => d.tokens || 0), 1);
    const todayStr = new Date().toISOString().slice(0, 10);

    container.innerHTML = days.map(d => {
        const h = maxVal > 0 ? Math.max(((d.tokens || 0) / maxVal * 100).toFixed(0), 2) : 0;
        const isToday = d.date === todayStr;
        const dayLabel = d.date.slice(5); // MM-DD
        return `
        <div class="chart-bar-group">
            <div class="chart-bar-value">${fmtShort(d.tokens)}</div>
            <div class="chart-bar-wrap">
                <div class="chart-bar" style="height:${h}%;${isToday?'background:linear-gradient(180deg,#a855f7,rgba(168,85,247,.5));box-shadow:0 0 8px rgba(168,85,247,.3);':''}"
                     title="${d.date}: ${fmtNum(d.tokens)} Token"></div>
            </div>
            <div class="chart-bar-label" style="${isToday?'color:#a855f7;font-weight:700':''}">${isToday ? '今天' : dayLabel}</div>
        </div>`;
    }).join('');
}

// ── Model Cards ──
function renderModels(models) {
    const container = document.getElementById('modelCards');
    if (!models.length) { container.innerHTML = '<div class="loading-placeholder">暂无模型数据</div>'; return; }
    const maxTokens = Math.max(...models.map(m => Math.max(m.total_tokens || 0, 1)), 1);

    container.innerHTML = models.map(m => {
        const barClass = modelBarClass(m.name);
        const barTokens = m.total_tokens || 0;
        const pct = Math.max((barTokens / maxTokens * 100).toFixed(0), 2);
        const cost = m.cost != null ? '¥' + (m.cost < 0.01 ? m.cost.toFixed(4) : m.cost.toFixed(2)) : '--';
        const u = m.usage || {};
        const input = (parseInt(u.PROMPT_TOKEN)||0)+(parseInt(u.PROMPT_CACHE_HIT_TOKEN)||0)+(parseInt(u.PROMPT_CACHE_MISS_TOKEN)||0);
        const output = parseInt(u.RESPONSE_TOKEN)||0;
        const hitRate = m.cache_hit_rate || 0;

        return `
        <div class="model-card">
            <div class="model-card-header">
                <span class="model-name">${esc(m.name)}</span>
                <span class="model-cost">${cost}</span>
            </div>
            <div class="model-bar-wrap">
                <div class="model-bar-info"><span>${fmtNum(barTokens)} Token</span><span>${pct}%</span></div>
                <div class="model-bar-bg"><div class="model-bar-fill ${barClass}" style="width:${pct}%"></div></div>
            </div>
            <div class="model-stats">
                <div class="model-stat-item"><div class="model-stat-value">${fmtNum(input)}</div><div class="model-stat-label">输入</div></div>
                <div class="model-stat-item"><div class="model-stat-value">${fmtNum(output)}</div><div class="model-stat-label">输出</div></div>
                <div class="model-stat-item"><div class="model-stat-value">${fmtNum(barTokens)}</div><div class="model-stat-label">总计</div></div>
                <div class="model-stat-item highlight"><div class="model-stat-value">${hitRate}%</div><div class="model-stat-label">缓存命中</div></div>
            </div>
        </div>`;
    }).join('');
}

async function refreshData() {
    try { await fetch('/api/refresh', { method: 'POST' }); await loadDashboard(); } catch(e) {}
}

async function toggleAutostart() {
    const btn = document.getElementById('autostartBtn');
    try {
        const sr = await fetch('/api/autostart/status');
        const st = await sr.json();
        if (st.enabled) {
            await fetch('/api/autostart/disable');
            btn.textContent = '开机自启';
            btn.style.background = '';
        } else {
            await fetch('/api/autostart/enable');
            btn.textContent = '已开启自启';
            btn.style.background = 'rgba(34,197,94,.15)';
            btn.style.color = '#22c55e';
        }
    } catch(e) {}
}

// Init autostart button state on dashboard load
async function initAutostart() {
    try {
        const sr = await fetch('/api/autostart/status');
        const st = await sr.json();
        if (st.enabled) {
            const btn = document.getElementById('autostartBtn');
            btn.textContent = '已开启自启';
            btn.style.background = 'rgba(34,197,94,.15)';
            btn.style.color = '#22c55e';
        }
    } catch(e) {}
}

async function foldWindow() {
    try { await fetch('/api/fold'); } catch(e) {}
}

async function expandWindow() {
    try { await fetch('/api/expand'); } catch(e) {}
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

document.addEventListener('DOMContentLoaded', () => {
    // Restore alert threshold
    const saved = localStorage.getItem('alertThreshold');
    if (saved) document.getElementById('alertThreshold').value = saved;

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }

    checkStatus();
    document.getElementById('codeInput').addEventListener('keydown', e => { if (e.key==='Enter') verifyCode(); });
    document.getElementById('phoneInput').addEventListener('keydown', e => { if (e.key==='Enter') startLogin(); });
});
