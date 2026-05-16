let sessionId = null;
let rollNo = null;

const App = {
    init() {
        const savedRollNo = localStorage.getItem('nsut_rollno');
        if (savedRollNo) {
            this.checkCache(savedRollNo);
        } else {
            this.renderLogin();
        }
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
                this.renderChat();
                this.addBotMessage("Welcome back! I've loaded your attendance from the local cache. \n\nType **HI** for a summary or **SW** for subject-wise details.");
            } else {
                localStorage.removeItem('nsut_rollno');
                this.renderLogin();
            }
        } catch (e) {
            this.renderLogin();
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

    renderLogin() {
        document.getElementById('app').innerHTML = `
            <div class="glass-panel auth-container">
                <h1>NSUT Smart Portal</h1>
                <p style="color: var(--text-secondary)">Login to analyze your attendance.</p>
                <div class="input-group">
                    <input type="text" id="rollno" placeholder="Roll No (e.g. 2024UME4116)">
                </div>
                <div class="input-group">
                    <input type="password" id="password" placeholder="Password">
                </div>
                <div class="input-group">
                    <input type="text" id="semester" placeholder="Semester (e.g. 4)" value="4">
                </div>
                <button id="loginBtn">Connect to Portal</button>
                <div id="captchaArea" style="display: none; flex-direction: column; gap: 1rem; margin-top: 1rem;">
                    <img id="captchaImg" style="border-radius: 8px; border: 1px solid var(--glass-border);">
                    <input type="text" id="captchaInput" placeholder="Enter Captcha">
                    <button id="verifyBtn">Verify & Deep Scrape</button>
                    <small style="color: var(--accent)">Deep scraping may take 10-15 seconds. It will save locally so you only do this once.</small>
                </div>
            </div>
        `;

        document.getElementById('loginBtn').addEventListener('click', async () => {
            const btn = document.getElementById('loginBtn');
            btn.innerHTML = '<div class="loader"></div>';
            
            const roll = document.getElementById('rollno').value;
            const pwd = document.getElementById('password').value;
            const sem = document.getElementById('semester').value;

            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rollno: roll, password: pwd, semester: sem })
            });
            const data = await res.json();
            
            if (data.success) {
                sessionId = data.session_id;
                rollNo = roll;
                btn.style.display = 'none';
                document.getElementById('captchaArea').style.display = 'flex';
                document.getElementById('captchaImg').src = data.captcha_base64;
            } else {
                btn.innerHTML = 'Connect to Portal';
                alert(data.message);
            }
        });

        document.getElementById('verifyBtn').addEventListener('click', async () => {
            const btn = document.getElementById('verifyBtn');
            btn.innerHTML = '<div class="loader"></div>';
            
            const cap = document.getElementById('captchaInput').value;
            const res = await fetch('/api/captcha', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, captcha: cap })
            });
            const data = await res.json();
            
            if (data.success) {
                localStorage.setItem('nsut_rollno', rollNo);
                this.renderChat();
                this.addBotMessage(data.message);
            } else {
                btn.innerHTML = 'Verify & Deep Scrape';
                alert(data.message);
            }
        });
    },

    renderChat() {
        document.getElementById('app').innerHTML = `
            <div class="glass-panel chat-container">
                <div class="chat-header">
                    <h2 style="margin: 0; font-size: 1.2rem;">Attendance Assistant</h2>
                    <button id="logoutBtn" style="padding: 0.5rem 1rem; font-size: 0.9rem; background: rgba(255,255,255,0.1); border-radius: 8px; color: white; border: none; cursor: pointer;">Log Out</button>
                </div>
                <div class="chat-messages" id="chatMessages"></div>
                <div class="chat-input-area">
                    <input type="text" id="chatInput" placeholder="Type HI for summary, SW for subject-wise...">
                    <button id="sendBtn">Send</button>
                </div>
            </div>
        `;

        document.getElementById('logoutBtn').addEventListener('click', () => {
            localStorage.removeItem('nsut_rollno');
            this.renderLogin();
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
