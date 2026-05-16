let sessionId = null;
let rollNo = null;
let autoOcrTried = false;
let captchaIssuedAt = 0;
let appConfig = {};

const App = {
    async init() {
        await this.loadConfig();
        const savedRollNo = localStorage.getItem('nsut_rollno') || appConfig.default_rollno || '';
        if (savedRollNo) {
            this.checkCache(savedRollNo);
        } else {
            this.renderLogin();
        }
    },

    async loadConfig() {
        try {
            const res = await fetch('/api/config');
            if (!res.ok) {
                throw new Error('Backend config endpoint unavailable');
            }
            appConfig = await res.json();
        } catch (e) {
            appConfig = { backend_stale: true };
        }
    },

    escapeAttr(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    },

    async checkCache(rollno) {
        this.renderLoading("Verifying local cache...");
        try {
            const res = await fetch('/api/check_cache', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rollno })
            });
            const data = await res.json();
            if (data.success) {
                sessionId = data.session_id;
                rollNo = rollno;
                this.renderChat(data.analysis);
                const cacheNote = data.cache_needs_refresh
                    ? "\n\n**Cache note:** this is an older totals-only cache. Type **TOTAL**, **SAFE**, or **RISK** now, but login once with CAPTCHA to rebuild the v2 cache for absent dates, profile, calendar marks, and portal data surfaces."
                    : "";
                this.addBotMessage("Welcome back! I've loaded your attendance from the local cache." + cacheNote + "\n\nType **HI** for a summary, **CODES** for shortcuts, or **SW** for subject-wise details.");
            } else {
                this.renderLogin(rollno);
            }
        } catch (e) {
            this.renderLogin(rollno);
        }
    },

    renderLoading(text) {
        document.getElementById('app').innerHTML = `
            <div class="glass-panel" style="margin: auto; padding: 3rem; text-align: center;">
                <div class="loader"></div>
                <p style="margin-top: 1rem; color: var(--text-secondary);">${text}</p>
            </div>
        `;
    },

    renderLogin(initialRoll = '') {
        const savedPassword = localStorage.getItem('nsut_portal_password') || '';
        const passwordPlaceholder = appConfig.has_saved_password ? 'Password saved in .env' : 'Password';
        const savedPasswordChecked = savedPassword ? 'checked' : '';
        const savedPasswordValue = this.escapeAttr(savedPassword);
        const savedRollValue = this.escapeAttr(initialRoll || localStorage.getItem('nsut_rollno') || appConfig.default_rollno || '');

        document.getElementById('app').innerHTML = `
            <div class="glass-panel auth-container">
                <h1>Attendance Assistant</h1>
                <p style="color: var(--text-secondary)">Connect once, then use the cached assistant workspace.</p>
                <div class="input-group">
                    <input type="text" id="rollno" placeholder="Roll No (e.g. 2024UME4116)" value="${savedRollValue}">
                </div>
                <div class="input-group">
                    <input type="password" id="password" placeholder="${passwordPlaceholder}" value="${savedPasswordValue}">
                </div>
                <label class="check-row">
                    <input type="checkbox" id="rememberPassword" ${savedPasswordChecked}>
                    <span>Remember password on this device</span>
                </label>
                <button id="loginBtn">Connect to Portal</button>
                <div id="captchaArea" style="display: none; flex-direction: column; gap: 1rem; margin-top: 1rem;">
                    <img id="captchaImg" style="border-radius: 8px; border: 1px solid var(--glass-border);">
                    <input type="text" id="captchaInput" placeholder="Enter Captcha">
                       <div style="display: flex; gap: 0.5rem;">
                           <button id="verifyBtn" style="flex: 1;">Verify & Deep Scrape</button>
                           <button id="autoOcrBtn" title="Use OCR to automatically read CAPTCHA" style="flex: 0; padding: 0.5rem 1rem; background: rgba(100, 200, 255, 0.3); border: 1px solid rgba(100, 200, 255, 0.5); cursor: pointer; border-radius: 8px; color: #64c8ff; font-weight: bold;">🤖 OCR</button>
                           <button id="refreshCaptchaBtn" title="Refresh to latest CAPTCHA from portal" style="flex: 0; padding: 0.5rem 1rem; background: rgba(255, 220, 120, 0.25); border: 1px solid rgba(255, 220, 120, 0.5); cursor: pointer; border-radius: 8px; color: #ffd166; font-weight: bold;">↻</button>
                       </div>
                       <small style="color: var(--accent)">💡 Tip: Use ↻ before entering CAPTCHA to ensure latest image, then Verify. OCR is optional.</small>
                </div>
            </div>
        `;

        document.getElementById('loginBtn').addEventListener('click', async () => {
            const btn = document.getElementById('loginBtn');
            btn.innerHTML = '<div class="loader"></div>';
            
            const roll = document.getElementById('rollno').value;
            const pwd = document.getElementById('password').value;
            const rememberPassword = document.getElementById('rememberPassword').checked;

            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rollno: roll, password: pwd })
            });
            const data = await res.json();
            
            if (data.success) {
                sessionId = data.session_id;
                rollNo = data.rollno || roll;
                localStorage.setItem('nsut_rollno', rollNo);
                if (rememberPassword && pwd) {
                    localStorage.setItem('nsut_portal_password', pwd);
                } else if (!rememberPassword) {
                    localStorage.removeItem('nsut_portal_password');
                }
                autoOcrTried = false;
                btn.style.display = 'none';
                document.getElementById('captchaArea').style.display = 'flex';
                document.getElementById('captchaImg').src = data.captcha_base64;
                captchaIssuedAt = Date.now();
            } else {
                btn.innerHTML = 'Connect to Portal';
                alert(data.message);
            }
        });

        document.getElementById('refreshCaptchaBtn').addEventListener('click', async () => {
            const btn = document.getElementById('refreshCaptchaBtn');
            const previous = btn.innerHTML;
            btn.innerHTML = '...';
            btn.disabled = true;

            try {
                const res = await fetch('/api/captcha/refresh', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId })
                });
                const data = await res.json();
                if (data.success && data.captcha_base64) {
                    document.getElementById('captchaImg').src = data.captcha_base64;
                    document.getElementById('captchaInput').value = '';
                    captchaIssuedAt = Date.now();
                } else {
                    const dbg = data.debug_dir ? `\n\nDebug folder: ${data.debug_dir}` : '';
                    alert((data.message || 'Could not refresh captcha') + dbg);
                }
            } catch (e) {
                alert('Refresh failed: ' + e.message);
            } finally {
                btn.innerHTML = previous;
                btn.disabled = false;
            }
        });

        document.getElementById('verifyBtn').addEventListener('click', async () => {
            const btn = document.getElementById('verifyBtn');
            btn.innerHTML = '<div class="loader"></div>';

            if (captchaIssuedAt && (Date.now() - captchaIssuedAt) > 45000) {
                try {
                    const refreshRes = await fetch('/api/captcha/refresh', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_id: sessionId })
                    });
                    const refreshData = await refreshRes.json();
                    if (refreshData.success && refreshData.captcha_base64) {
                        document.getElementById('captchaImg').src = refreshData.captcha_base64;
                        document.getElementById('captchaInput').value = '';
                        captchaIssuedAt = Date.now();
                        btn.innerHTML = 'Verify & Deep Scrape';
                        alert('Captcha was refreshed because previous one got old. Please type the new captcha and submit again.');
                        return;
                    }
                } catch (e) {
                    // fallback to existing flow
                }
            }
            
            const cap = document.getElementById('captchaInput').value;
            const res = await fetch('/api/captcha', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, captcha: cap })
            });
            const data = await res.json();
            
            if (data.success) {
                localStorage.setItem('nsut_rollno', rollNo);
                this.renderChat(data.data);
                this.addBotMessage(data.message + "\n\nType **HI** for the full dashboard, **CODES** for shortcuts, or ask a subject code like **MEMEC303**.");
            } else {
                btn.innerHTML = 'Verify & Deep Scrape';
                if (data.retryable && data.captcha_base64) {
                    document.getElementById('captchaImg').src = data.captcha_base64;
                    captchaIssuedAt = Date.now();
                }
                const dbg = data.debug_dir ? `\n\nDebug folder: ${data.debug_dir}` : '';
                alert((data.message || 'Verification failed') + dbg);
            }
        });
       
           document.getElementById('autoOcrBtn').addEventListener('click', async () => {
               const btn = document.getElementById('autoOcrBtn');
               const originalText = btn.innerHTML;
               btn.innerHTML = '⏳ Reading...';
               btn.disabled = true;
           
               try {
                   const res = await fetch('/api/captcha', {
                       method: 'POST',
                       headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ session_id: sessionId, auto_ocr: true })
                   });
                   const data = await res.json();
               
                   if (data.success) {
                       localStorage.setItem('nsut_rollno', rollNo);
                       this.renderChat(data.data);
                       this.addBotMessage("CAPTCHA auto-read with OCR. " + data.message + "\n\nType **HI** for the full dashboard or **CODES** for shortcuts.");
                   } else {
                       btn.innerHTML = originalText;
                       btn.disabled = false;
                       if (data.retryable && data.captcha_base64) {
                           document.getElementById('captchaImg').src = data.captcha_base64;
                           captchaIssuedAt = Date.now();
                       }
                       const dbg = data.debug_dir ? `\n\nDebug folder: ${data.debug_dir}` : '';
                       alert("❌ OCR failed: " + data.message + "\n\nYou can retry OCR or enter CAPTCHA manually without re-login." + dbg);
                   }
               } catch (e) {
                   btn.innerHTML = originalText;
                   btn.disabled = false;
                   alert("❌ Error: " + e.message);
               }
           });
    },

    renderChat(analysis = null) {
        const insights = analysis && analysis.insights ? analysis.insights : null;
        const student = analysis && analysis.student ? analysis.student : {};
        const source = analysis && analysis.source ? analysis.source : {};
        const headerMeta = insights
            ? `${insights.overall_percentage || 0}% - ${insights.total_attended || 0}/${insights.total_classes || 0} - ${insights.total_absent || 0} absent${source.legacy_cache ? ' - legacy cache' : ''}`
            : 'Smart attendance workspace';
        const studentName = student.name || rollNo || 'Attendance Assistant';

        document.getElementById('app').innerHTML = `
            <div class="glass-panel chat-container">
                <div class="chat-header">
                    <div>
                        <h2 style="margin: 0; font-size: 1.2rem;">${studentName}</h2>
                        <div class="chat-subtitle">${headerMeta}</div>
                    </div>
                    <button id="logoutBtn" style="padding: 0.5rem 1rem; font-size: 0.9rem; background: rgba(255,255,255,0.1); border-radius: 8px; color: white; border: none; cursor: pointer;">Log Out</button>
                </div>
                <div class="chat-messages" id="chatMessages"></div>
                <div class="quick-actions">
                    <button class="quick-chip" data-message="HI">HI</button>
                    <button class="quick-chip" data-message="SW">SW</button>
                    <button class="quick-chip" data-message="TOTAL">TOTAL</button>
                    <button class="quick-chip" data-message="ABSENT">ABSENT</button>
                    <button class="quick-chip" data-message="SAFE">SAFE</button>
                    <button class="quick-chip" data-message="RISK">RISK</button>
                    <button class="quick-chip" data-message="PROFILE">PROFILE</button>
                </div>
                <div class="chat-input-area">
                    <input type="text" id="chatInput" placeholder="Type HI for summary, SW for subject-wise...">
                    <button id="sendBtn">Send</button>
                </div>
            </div>
        `;

        document.getElementById('logoutBtn').addEventListener('click', () => {
            sessionId = null;
            this.renderLogin(rollNo);
        });

        const sendMsg = async () => {
            const input = document.getElementById('chatInput');
            const msg = input.value.trim();
            if (!msg) return;

            this.addUserMessage(msg);
            input.value = '';

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId, message: msg })
                });
                const data = await res.json();
                this.addBotMessage(data.reply);
            } catch (e) {
                this.addBotMessage("Error connecting to server.");
            }
        };

        document.getElementById('sendBtn').addEventListener('click', sendMsg);
        document.getElementById('chatInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMsg();
        });
        document.querySelectorAll('.quick-chip').forEach((button) => {
            button.addEventListener('click', () => {
                document.getElementById('chatInput').value = button.dataset.message;
                sendMsg();
            });
        });
    },

    addUserMessage(text) {
        const div = document.createElement('div');
        div.className = 'message user';
        div.textContent = text;
        document.getElementById('chatMessages').appendChild(div);
        this.scrollToBottom();
    },

    addBotMessage(markdown) {
        const div = document.createElement('div');
        div.className = 'message bot';
        
        // Very simple markdown parser for bold, lists, and tables
        let html = markdown
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
        
        // Handle tables (basic implementation)
        if (html.includes('|')) {
            const lines = html.split('<br>');
            let inTable = false;
            let tableHtml = '<table style="width:100%; border-collapse: collapse; margin-top: 10px;">';
            
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line.startsWith('|')) {
                    inTable = true;
                    if (line.includes('---')) {
                        lines[i] = ''; 
                        continue; 
                    }
                    
                    const cells = line.split('|').filter(c => c.trim() !== '');
                    tableHtml += '<tr>';
                    cells.forEach(c => {
                        tableHtml += `<td style="border: 1px solid var(--glass-border); padding: 8px;">${c.trim()}</td>`;
                    });
                    tableHtml += '</tr>';
                    lines[i] = ''; // clear line
                } else if (inTable) {
                    inTable = false;
                    tableHtml += '</table>';
                    lines[i] = tableHtml + '<br>' + lines[i];
                    tableHtml = '';
                }
            }
            if (inTable) tableHtml += '</table>';
            html = lines.filter(l => l !== '').join('<br>');
            if (inTable) html += tableHtml;
        }

        div.innerHTML = html;
        document.getElementById('chatMessages').appendChild(div);
        this.scrollToBottom();
    },

    scrollToBottom() {
        const msgs = document.getElementById('chatMessages');
        msgs.scrollTop = msgs.scrollHeight;
    }
};

document.addEventListener('DOMContentLoaded', () => App.init());
