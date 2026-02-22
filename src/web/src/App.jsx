import { useState, useRef, useEffect } from 'react'
import axios from 'axios'

function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [serverStatus, setServerStatus] = useState('checking')
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    // Check API health
    axios.get('http://localhost:9001/health')
      .then(() => setServerStatus('online'))
      .catch(() => setServerStatus('offline'))
  }, [])

  const sendMessage = async () => {
    if (!input.trim() || loading) return

    const userMessage = { role: 'user', content: input }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await axios.post('http://localhost:9001/chat', {
        userId: 'web-user',
        message: input
      })

      const assistantMessage = {
        role: 'assistant',
        content: response.data.answer,
        debug: response.data.debug
      }
      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage = {
        role: 'assistant',
        content: `Error: ${error.response?.data?.detail || error.message}`,
        isError: true
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearChat = () => {
    setMessages([])
    setInput('')
  }

  return (
    <div className="app-container">
      <header className="header">
        <h1>Zava Retail Orchestrator</h1>
        <p>AI-Powered Retail Operations Assistant</p>
        <div className="header-actions">
          <span className={`status ${serverStatus}`}>
            {serverStatus === 'online' ? '● Connected' : serverStatus === 'offline' ? '● Offline' : '● Checking...'}
          </span>
          {messages.length > 0 && (
            <button className="new-chat-btn" onClick={clearChat}>
              ← New Chat
            </button>
          )}
        </div>
      </header>

      <main className="chat-container">
        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <h2>Welcome to Zava Retail Orchestrator</h2>
              <p>Ask me about:</p>
              <ul>
                <li>Store operations and shelf execution</li>
                <li>Inventory management and out-of-stocks</li>
                <li>Planogram compliance issues</li>
              </ul>
              <div className="examples">
                <p>Example questions:</p>
                <button onClick={() => setInput('What should I do if planogram compliance is low?')}>
                  Planogram compliance issues
                </button>
                <button onClick={() => setInput('Why are out-of-stocks high in Store 457?')}>
                  Out-of-stock analysis
                </button>
                <button onClick={() => setInput('What store ops actions should I take when shelf execution is poor?')}>
                  Shelf execution help
                </button>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} className={`message ${msg.role} ${msg.isError ? 'error' : ''}`}>
              <div className="message-content">
                {msg.content.split('\n').map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
              {msg.debug && msg.debug.sub_agents_used && (
                <div className="debug-info">
                  <span>Agents: {msg.debug.sub_agents_used.join(', ')}</span>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="message assistant loading">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about store operations, inventory, or planograms..."
            disabled={loading || serverStatus === 'offline'}
            rows={1}
          />
          <button onClick={sendMessage} disabled={loading || !input.trim() || serverStatus === 'offline'}>
            {loading ? 'Sending...' : 'Send'}
          </button>
        </div>
      </main>

      <footer className="footer">
        <p>Powered by Azure AI Foundry &amp; Connected Agents</p>
      </footer>
    </div>
  )
}

export default App
