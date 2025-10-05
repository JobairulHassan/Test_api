import streamlit as st
# import ollama
import json
import os
import re
from datetime import datetime
from pathlib import Path

# Page configuration
st.set_page_config(
    page_title="AI Chat Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for beautiful UI
st.markdown("""
<style>
    /* Main chat container 
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    */
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #2d3748 0%, #1a202c 100%);
    }
    
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label {
        color: #e2e8f0 !important;
    }
    
    /* Chat messages */
    .user-message {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem 1.5rem;
        border-radius: 18px 18px 4px 18px;
        margin: 0.5rem 0;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        max-width: 80%;
        margin-left: auto;
        display: inline-block;
        width: fit-content;
        word-wrap: break-word;
    }
    
    .assistant-message {
        
        padding: 1rem 1.5rem;
        border-radius: 18px 18px 18px 4px;
        margin: 0.5rem 0;
        color: #2d3748;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        max-width: 80%;
        margin-right: auto;
        display: inline-block;
        width: fit-content;
        word-wrap: break-word;
    }
    
    .message-container-right {
        display: flex;
        justify-content: flex-end;
        margin: 0.5rem 0;
    }
    
    .message-container-left {
        display: flex;
        justify-content: flex-start;
        margin: 0.5rem 0;
    }
    
    /* Code blocks */
    .code-container {
        position: relative;
        margin: 1rem 0;
        background: #1e1e1e;
        border-radius: 8px;
        overflow: hidden;
    }
    
    .code-header {
        background: #2d2d2d;
        padding: 0.5rem 1rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid #404040;
    }
    
    .code-language {
        color: #858585;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    
    .copy-button {
        background: #667eea;
        color: white;
        border: none;
        padding: 0.4rem 1rem;
        border-radius: 5px;
        cursor: pointer;
        font-size: 0.85rem;
        transition: all 0.3s ease;
    }
    
    .copy-button:hover {
        background: #764ba2;
        transform: translateY(-2px);
    }
    
    .code-content {
        padding: 1rem;
        overflow-x: auto;
        color: #d4d4d4;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        line-height: 1.5;
    }
    
    .code-content pre {
        margin: 0;
        white-space: pre-wrap;
        word-wrap: break-word;
    }
    
    /* Greeting card */
    .greeting-card {
        background: white;
        padding: 2rem;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        text-align: center;
        margin: 2rem auto;
        max-width: 600px;
    }
    
    .greeting-card h1 {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        margin-bottom: 1rem;
    }
    
    .greeting-card p {
        color: #4a5568;
        font-size: 1.1rem;
        line-height: 1.6;
    }
    
    /* Chat input */
    .stChatInput {
        border-radius: 25px;
    }
    
    /* Buttons */
    .stButton button {
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
    }
    
    /* Sidebar footer */
    .sidebar-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        padding: 1rem;
        background: #1a202c;
        border-top: 1px solid #2d3748;
        color: #a0aec0;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = {}
if 'current_chat_id' not in st.session_state:
    st.session_state.current_chat_id = None
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None

# Directory for storing chat histories
CHAT_HISTORY_DIR = Path("chat_histories")
CHAT_HISTORY_DIR.mkdir(exist_ok=True)

# Helper functions
def save_chat_history(username, chat_id, messages):
    """Save chat history to file"""
    user_dir = CHAT_HISTORY_DIR / username
    user_dir.mkdir(exist_ok=True)
    
    chat_file = user_dir / f"{chat_id}.json"
    chat_data = {
        'id': chat_id,
        'timestamp': datetime.now().isoformat(),
        'messages': messages
    }
    
    with open(chat_file, 'w') as f:
        json.dump(chat_data, f, indent=2)

def load_chat_histories(username):
    """Load all chat histories for a user"""
    user_dir = CHAT_HISTORY_DIR / username
    if not user_dir.exists():
        return {}
    
    histories = {}
    for chat_file in user_dir.glob("*.json"):
        with open(chat_file, 'r') as f:
            chat_data = json.load(f)
            histories[chat_data['id']] = chat_data
    
    return histories

def create_new_chat():
    """Create a new chat session"""
    st.session_state.messages = []
    st.session_state.current_chat_id = datetime.now().strftime("%Y%m%d_%H%M%S")

def get_chat_title(messages):
    """Generate a title from the first user message"""
    for msg in messages:
        if msg['role'] == 'user':
            return msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
    return "New Chat"

def delete_chat_history(username, chat_id):
    """Delete a specific chat history"""
    user_dir = CHAT_HISTORY_DIR / username
    chat_file = user_dir / f"{chat_id}.json"
    
    if chat_file.exists():
        chat_file.unlink()
        return True
    return False

def parse_message_with_code(content):
    """Parse message content and extract code blocks"""
    # Pattern to match code blocks with optional language
    code_pattern = r'```(\w+)?\n(.*?)```'
    
    parts = []
    last_end = 0
    
    for match in re.finditer(code_pattern, content, re.DOTALL):
        # Add text before code block
        if match.start() > last_end:
            text_content = content[last_end:match.start()].strip()
            if text_content:
                parts.append({'type': 'text', 'content': text_content})
        
        # Add code block
        language = match.group(1) or 'code'
        code_content = match.group(2).strip()
        parts.append({
            'type': 'code',
            'language': language,
            'content': code_content
        })
        
        last_end = match.end()
    
    # Add remaining text
    if last_end < len(content):
        text_content = content[last_end:].strip()
        if text_content:
            parts.append({'type': 'text', 'content': text_content})
    
    # If no code blocks found, return the whole content as text
    if not parts:
        parts.append({'type': 'text', 'content': content})
    
    return parts

def render_code_block(language, code, index):
    """Render a code block with copy functionality"""
    code_id = f"code_{index}"
    
    st.markdown(f"""
    <div class='code-container'>
        <div class='code-header'>
            <span class='code-language'>{language}</span>
            <button class='copy-button' onclick='copyCode("{code_id}")'>📋 Copy</button>
        </div>
        <div class='code-content'>
            <pre id='{code_id}'>{code}</pre>
        </div>
    </div>
    
    <script>
    function copyCode(id) {{
        const code = document.getElementById(id).textContent;
        navigator.clipboard.writeText(code).then(function() {{
            const button = event.target;
            const originalText = button.textContent;
            button.textContent = '✓ Copied!';
            setTimeout(function() {{
                button.textContent = originalText;
            }}, 2000);
        }});
    }}
    </script>
    """, unsafe_allow_html=True)

# def chat_with_ollama(messages, model="llama2"):
#     """Send messages to Ollama and get response"""
#     try:
#         response = ollama.chat(
#             model=model,
#             messages=messages
#         )
#         return response['message']['content']
#     except Exception as e:
#         return f"Error: {str(e)}"

# Sidebar
with st.sidebar:
    st.markdown("### 🤖 AI Chat Assistant")
    st.markdown("---")
    
    # Login/Logout section
    if not st.session_state.logged_in:
        st.markdown("#### 🔐 Login")
        username_input = st.text_input("Username", key="username_input")
        if st.button("Login", use_container_width=True):
            if username_input:
                st.session_state.logged_in = True
                st.session_state.username = username_input
                st.session_state.chat_history = load_chat_histories(username_input)
                st.rerun()
            else:
                st.error("Please enter a username")
    else:
        st.success(f"👤 Logged in as: **{st.session_state.username}**")
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.messages = []
            st.session_state.current_chat_id = None
            st.rerun()
    
    st.markdown("---")
    
    # New Chat button
    if st.button("➕ New Chat", use_container_width=True):
        create_new_chat()
        st.rerun()
    
    st.markdown("---")
    
    # Chat History
    if st.session_state.logged_in and st.session_state.chat_history:
        st.markdown("#### 📚 Chat History")
        
        # Sort chats by timestamp (newest first)
        sorted_chats = sorted(
            st.session_state.chat_history.items(),
            key=lambda x: x[1]['timestamp'],
            reverse=True
        )
        
        for chat_id, chat_data in sorted_chats:
            title = get_chat_title(chat_data['messages'])
            timestamp = datetime.fromisoformat(chat_data['timestamp']).strftime("%Y-%m-%d %H:%M")
            
            # Create columns for chat button and delete button
            col1, col2 = st.columns([4, 1])
            
            with col1:
                if st.button(
                    f"💬 {title}\n🕒 {timestamp}",
                    key=f"chat_{chat_id}",
                    use_container_width=True
                ):
                    st.session_state.messages = chat_data['messages']
                    st.session_state.current_chat_id = chat_id
                    st.rerun()
            
            with col2:
                if st.button("🗑️", key=f"delete_{chat_id}", help="Delete this chat"):
                    if delete_chat_history(st.session_state.username, chat_id):
                        # If deleting current chat, clear messages
                        if st.session_state.current_chat_id == chat_id:
                            st.session_state.messages = []
                            st.session_state.current_chat_id = None
                        
                        # Reload chat history
                        st.session_state.chat_history = load_chat_histories(st.session_state.username)
                        st.success("Chat deleted successfully!")
                        st.rerun()
                    else:
                        st.error("Failed to delete chat")
    elif st.session_state.logged_in:
        st.info("No chat history yet. Start chatting!")
    else:
        st.info("Login to save and view chat history")
    
    # Footer
    st.markdown("---")
    st.markdown(f"""
    <div style='text-align: center; color: #a0aec0; font-size: 0.85rem; padding: 1rem 0;'>
        👤 {st.session_state.username if st.session_state.logged_in else 'Guest'}<br>
        <small>© 2025 AI Chat Assistant</small>
    </div>
    """, unsafe_allow_html=True)

# Main chat area
if len(st.session_state.messages) == 0:
    # Greeting message
    st.markdown("""
    <div class='greeting-card'>
        <h1>👋 Welcome to AI Chat Assistant!</h1>
        <p>I'm here to help you with any questions or tasks you have.</p>
        <p>✨ <strong>Start a conversation below</strong> and I'll assist you right away!</p>
        <p style='margin-top: 1.5rem; color: #718096;'>
            💡 Tip: Login to save your chat history and continue conversations later.
        </p>
    </div>
    """, unsafe_allow_html=True)
else:
    # Display chat messages
    for idx, message in enumerate(st.session_state.messages):
        if message['role'] == 'user':
            st.markdown(f"""
            <div class='message-container-right'>
                <div class='user-message'>
                    {message['content']}
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Parse message for code blocks
            parts = parse_message_with_code(message['content'])
            
            st.markdown("<div class='message-container-left'>", unsafe_allow_html=True)
            st.markdown("<div class='assistant-message'>", unsafe_allow_html=True)
            st.markdown("<strong>🤖 Assistant</strong>", unsafe_allow_html=True)
            
            for part_idx, part in enumerate(parts):
                if part['type'] == 'text':
                    st.markdown(f"<p>{part['content']}</p>", unsafe_allow_html=True)
                elif part['type'] == 'code':
                    st.markdown("</div></div>", unsafe_allow_html=True)  # Close message containers
                    render_code_block(part['language'], part['content'], f"{idx}_{part_idx}")
                    st.markdown("<div class='message-container-left'><div class='assistant-message'>", unsafe_allow_html=True)  # Reopen
            
            st.markdown("</div></div>", unsafe_allow_html=True)

# Chat input
if prompt := st.chat_input("Type your message here..."):
    # Add user message
    st.session_state.messages.append({'role': 'user', 'content': prompt})
    
    # Create new chat ID if this is the first message of a new chat
    if st.session_state.current_chat_id is None:
        st.session_state.current_chat_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Get assistant response
    with st.spinner("🤔 Thinking..."):
        response = "Output demo"
        # response = chat_with_ollama(st.session_state.messages)
    
    # Add assistant message
    st.session_state.messages.append({'role': 'assistant', 'content': response})
    
    # Save chat history if logged in
    if st.session_state.logged_in:
        save_chat_history(
            st.session_state.username,
            st.session_state.current_chat_id,
            st.session_state.messages
        )
        st.session_state.chat_history = load_chat_histories(st.session_state.username)
    
    st.rerun()
