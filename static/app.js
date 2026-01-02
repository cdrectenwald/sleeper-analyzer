// Sleeper Analyzer Chat App

const chatContainer = document.getElementById('chat-container');
const chatForm = document.getElementById('chat-form');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const seasonSelect = document.getElementById('season');

// Conversation history for context
let conversationHistory = [];

// Add a message to the chat
function addMessage(content, type = 'assistant', metadata = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;
    
    messageDiv.appendChild(contentDiv);
    
    // Add confidence indicator for assistant messages
    if (type === 'assistant' && metadata && metadata.confidence) {
        const confidenceDiv = document.createElement('div');
        confidenceDiv.className = `confidence confidence-${metadata.confidence}`;
        const confidenceLabels = {
            'high': 'High confidence - based on your league data',
            'medium': 'Medium confidence - partial data available',
            'low': 'Low confidence - limited data, may need clarification'
        };
        confidenceDiv.textContent = confidenceLabels[metadata.confidence] || metadata.confidence;
        messageDiv.appendChild(confidenceDiv);
    }
    
    // Add follow-up suggestions if available
    if (type === 'assistant' && metadata && metadata.follow_up_suggestions && metadata.follow_up_suggestions.length > 0) {
        const suggestionsDiv = document.createElement('div');
        suggestionsDiv.className = 'suggestions';
        suggestionsDiv.innerHTML = '<span class="suggestions-label">Try asking:</span> ';
        
        metadata.follow_up_suggestions.forEach((suggestion, index) => {
            const btn = document.createElement('button');
            btn.className = 'suggestion-btn';
            btn.textContent = suggestion;
            btn.onclick = () => {
                messageInput.value = suggestion;
                messageInput.focus();
            };
            suggestionsDiv.appendChild(btn);
            if (index < metadata.follow_up_suggestions.length - 1) {
                suggestionsDiv.appendChild(document.createTextNode(' '));
            }
        });
        
        messageDiv.appendChild(suggestionsDiv);
    }
    
    chatContainer.appendChild(messageDiv);
    
    // Scroll to bottom
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    return contentDiv;
}

// Set loading state
function setLoading(isLoading) {
    sendBtn.disabled = isLoading;
    messageInput.disabled = isLoading;
    
    const btnText = sendBtn.querySelector('.btn-text');
    const btnLoading = sendBtn.querySelector('.btn-loading');
    
    btnText.hidden = isLoading;
    btnLoading.hidden = !isLoading;
}

// Send message to API
async function sendMessage(message) {
    const season = seasonSelect.value;
    
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                season: season,
                history: conversationHistory.slice(-10),  // Send last 10 messages
            }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error:', error);
        throw error;
    }
}

// Handle form submission
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const message = messageInput.value.trim();
    if (!message) return;
    
    // Add user message to UI and history
    addMessage(message, 'user');
    conversationHistory.push({ role: 'user', content: message });
    messageInput.value = '';
    
    // Set loading state
    setLoading(true);
    
    try {
        // Get response from API
        const response = await sendMessage(message);
        
        // Add assistant message to UI and history
        addMessage(response.answer, 'assistant', {
            confidence: response.confidence,
            follow_up_suggestions: response.follow_up_suggestions
        });
        conversationHistory.push({ role: 'assistant', content: response.answer });
        
    } catch (error) {
        addMessage('Sorry, something went wrong. Please try again.', 'error');
    } finally {
        setLoading(false);
        messageInput.focus();
    }
});

// Clear history when season changes
seasonSelect.addEventListener('change', () => {
    conversationHistory = [];
    // Optionally clear chat UI too
    // chatContainer.innerHTML = '';
});

// Focus input on load
messageInput.focus();

// Allow Ctrl+Enter to submit
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
        chatForm.dispatchEvent(new Event('submit'));
    }
});
