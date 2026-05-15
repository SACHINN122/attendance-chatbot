const BASE_URL = 'http://localhost:5000/api';

// DOM Elements
const loginContainer = document.getElementById('login-container');
const chatContainer = document.getElementById('chat-container');
const loginForm = document.getElementById('login-form');
const captchaForm = document.getElementById('captcha-form');
const captchaImg = document.getElementById('captcha-img');
const captchaInput = document.getElementById('captcha-input');
const captchaBtn = document.getElementById('captcha-btn');
const semesterSelect = document.getElementById('semester');
const loginError = document.getElementById('login-error');
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const logoutBtn = document.getElementById('logout-btn');
const loginBtn = document.getElementById('login-btn');

let currentSessionId = null;

// Login Step 1: Credentials
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const rollno = document.getElementById('rollno').value;
    const password = document.getElementById('password').value;
    const semester = semesterSelect.value;

    loginBtn.textContent = 'Loading Captcha...';
    loginBtn.disabled = true;
    loginError.textContent = '';

    try {
        const response = await fetch(`${BASE_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rollno, password, semester })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            currentSessionId = data.session_id;
            captchaImg.src = data.captcha_base64;
            loginForm.classList.add('hidden');
            captchaForm.classList.remove('hidden');
        } else {
            loginError.textContent = data.message || 'Login failed.';
        }
    } catch (error) {
        loginError.textContent = 'Could not connect to the server.';
        console.error(error);
    } finally {
        loginBtn.textContent = 'Next';
        loginBtn.disabled = false;
    }
});

// Login Step 2: Captcha
captchaForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const captcha = captchaInput.value;

    captchaBtn.textContent = 'Fetching Attendance... (This takes a few seconds)';
    captchaBtn.disabled = true;
    loginError.textContent = '';

    try {
        const response = await fetch(`${BASE_URL}/captcha`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, captcha })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            loginContainer.classList.add('hidden');
            chatContainer.classList.remove('hidden');
            addMessage(data.message, 'bot');
        } else {
            loginError.textContent = data.message || 'Captcha failed. Please try again.';
            captchaForm.classList.add('hidden');
            loginForm.classList.remove('hidden');
        }
    } catch (error) {
        loginError.textContent = 'Could not connect to the server.';
        console.error(error);
    } finally {
        captchaBtn.textContent = 'Login & Sync';
        captchaBtn.disabled = false;
        captchaInput.value = '';
    }
});

// Logout Event
logoutBtn.addEventListener('click', () => {
    chatContainer.classList.add('hidden');
    loginContainer.classList.remove('hidden');
    captchaForm.classList.add('hidden');
    loginForm.classList.remove('hidden');
    document.getElementById('password').value = '';
    chatMessages.innerHTML = '';
    currentSessionId = null;
});

// Send Message Event
const sendMessage = async () => {
    const message = userInput.value.trim();
    if (!message) return;

    // Display user message
    addMessage(message, 'user');
    userInput.value = '';

    // Simulate typing indicator
    const typingId = addMessage('...', 'bot', true);

    try {
        const response = await fetch(`${BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, message })
        });
        
        const data = await response.json();
        
        // Remove typing indicator and add real message
        document.getElementById(typingId).remove();
        
        if (response.ok) {
            addMessage(data.reply, 'bot');
        } else {
            addMessage('Error: ' + (data.reply || 'Server error.'), 'bot');
        }
    } catch (error) {
        document.getElementById(typingId).remove();
        addMessage('Sorry, I could not connect to the server.', 'bot');
        console.error(error);
    }
};

sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// Helper: Add message to chat
function addMessage(text, sender, isTyping = false) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', sender);
    
    // Parse tables and markdown
    let formattedText = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
        
    // Simple table parser
    if (formattedText.includes('|')) {
        const lines = formattedText.split('<br>');
        let inTable = false;
        let tableHtml = '';
        
        for (let i = 0; i < lines.length; i++) {
            let line = lines[i].trim();
            if (line.startsWith('|') && line.endsWith('|')) {
                if (!inTable) {
                    inTable = true;
                    tableHtml = '<table class="attendance-table">';
                }
                
                // Skip separator row
                if (line.includes('---')) continue;
                
                const cells = line.split('|').filter(c => c.trim() !== '');
                tableHtml += '<tr>';
                
                const isHeader = !tableHtml.includes('</tr>'); // First row is header
                
                cells.forEach(cell => {
                    tableHtml += isHeader ? `<th>${cell.trim()}</th>` : `<td>${cell.trim()}</td>`;
                });
                
                tableHtml += '</tr>';
                lines[i] = ''; // clear line
            } else if (inTable) {
                inTable = false;
                tableHtml += '</table>';
                lines[i-1] = tableHtml;
            }
        }
        
        if (inTable) {
            lines[lines.length-1] = tableHtml + '</table>';
        }
        
        formattedText = lines.filter(l => l !== '').join('<br>');
    }
        
    msgDiv.innerHTML = formattedText;
    
    const id = 'msg-' + Date.now();
    msgDiv.id = id;
    
    if (isTyping) {
        msgDiv.style.opacity = '0.5';
    }
    
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return id;
}
