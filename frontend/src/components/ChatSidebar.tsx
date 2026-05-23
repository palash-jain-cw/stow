import { useEffect, useRef, useState } from 'react'
import { Send, Paperclip, Bot, User, AlertCircle, RotateCcw } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ProposalCard, type Proposal } from './ProposalCard'

// ── Types ──────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string
  role: 'user' | 'agent'
  content: string
  streaming?: boolean
  proposal?: Proposal       // set when content contains a PROPOSAL: line
  proposalDisplay?: string  // display text with PROPOSAL: line stripped
}

// ── Proposal parsing ───────────────────────────────────────────────────────

const PROPOSAL_PREFIX = 'PROPOSAL:'

function proposalAmount(proposal: Proposal & { amount?: number }): number {
  return proposal.amount_paise ?? proposal.amount ?? 0
}

function normalizeProposal(raw: Proposal & { amount?: number }): Proposal {
  const normalized: Proposal = {
    ...raw,
    amount_paise: proposalAmount(raw),
    narration: raw.narration ?? '',
    from_account_name: raw.from_account_name ?? '',
    to_account_name: raw.to_account_name ?? '',
  }
  if (raw.tags?.length) {
    normalized.tags = raw.tags.filter((t) => typeof t === 'string' && t.trim()).map((t) => t.trim())
  }
  return normalized
}

function buildConfirmMessage(proposal: Proposal & { amount?: number }): string {
  const normalized = normalizeProposal(proposal)
  const payload: Record<string, unknown> = { ...normalized }
  if (!normalized.tags?.length) {
    delete payload.tags
  }
  return `confirm:${JSON.stringify(payload)}`
}

function parseProposal(content: string): { proposal: Proposal; display: string } | null {
  for (const line of content.split('\n')) {
    if (line.startsWith(PROPOSAL_PREFIX)) {
      try {
        const proposal = JSON.parse(line.slice(PROPOSAL_PREFIX.length)) as Proposal
        const display = content
          .split('\n')
          .filter(l => !l.startsWith(PROPOSAL_PREFIX))
          .join('\n')
          .trim()
        return { proposal, display }
      } catch {
        return null
      }
    }
  }
  return null
}

type WsStatus = 'connecting' | 'open' | 'error'

// ── Constants ──────────────────────────────────────────────────────────────

const WS_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000')
  .replace(/^http/, 'ws') + '/chat/ws'

// ── ChatSidebar ────────────────────────────────────────────────────────────

export function ChatSidebar() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [progressLabel, setProgressLabel] = useState('')
  const [status, setStatus] = useState<WsStatus>('connecting')

  const wsRef = useRef<WebSocket | null>(null)
  const pendingIdRef = useRef<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // WebSocket lifecycle
  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      setStatus('connecting')

      ws.onopen = () => setStatus('open')

      ws.onmessage = ({ data }: MessageEvent<string>) => {
        const msg = JSON.parse(data) as { type: string; content?: string; label?: string }
        if (msg.type === 'progress') {
          setProgressLabel(msg.label ?? '')
        } else if (msg.type === 'token' && msg.content !== undefined) {
          if (pendingIdRef.current) {
            setMessages(prev => prev.map(m =>
              m.id === pendingIdRef.current
                ? { ...m, content: m.content + msg.content }
                : m
            ))
          } else {
            const id = crypto.randomUUID()
            pendingIdRef.current = id
            setMessages(prev => [
              ...prev,
              { id, role: 'agent', content: msg.content!, streaming: true },
            ])
          }
        } else if (msg.type === 'done') {
          if (pendingIdRef.current) {
            const doneId = pendingIdRef.current
            setMessages(prev => prev.map(m => {
              if (m.id !== doneId) return m
              const parsed = parseProposal(m.content)
              return parsed
                ? { ...m, streaming: false, proposal: parsed.proposal, proposalDisplay: parsed.display }
                : { ...m, streaming: false }
            }))
            pendingIdRef.current = null
          }
          setIsTyping(false)
          setProgressLabel('')
        }
      }

      ws.onerror = () => setStatus('error')
      ws.onclose = () => {
        setStatus('error')
        reconnectTimer = setTimeout(connect, 2000)
      }
    }

    connect()
    return () => {
      reconnectTimer && clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [])

  // Scroll to bottom when messages or typing indicator change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  function send(text: string) {
    const ws = wsRef.current
    if (!text.trim() || !ws || ws.readyState !== WebSocket.OPEN) return

    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', content: text }])
    setIsTyping(true)
    setProgressLabel('')
    pendingIdRef.current = null
    ws.send(JSON.stringify({ type: 'text', content: text }))
    setInput('')
  }

  function sendFile(file: File) {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return

    const reader = new FileReader()
    reader.onload = () => {
      const b64 = (reader.result as string).split(',')[1]
      setMessages(prev => [
        ...prev,
        { id: crypto.randomUUID(), role: 'user', content: `📎 ${file.name}` },
      ])
      setIsTyping(true)
      setProgressLabel('')
      pendingIdRef.current = null
      ws.send(JSON.stringify({
        type: 'file',
        content: b64,
        mime_type: file.type,
        filename: file.name,
      }))
    }
    reader.readAsDataURL(file)
  }

  const showDots = isTyping && !pendingIdRef.current

  return (
    <div className="flex flex-col w-72 border-l border-zinc-200 bg-white h-screen shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-100 shrink-0">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-zinc-500" />
          <span className="text-sm font-semibold text-zinc-800">Stow</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setMessages([]); pendingIdRef.current = null; setIsTyping(false) }}
            disabled={messages.length === 0}
            className="p-1 text-zinc-400 hover:text-zinc-600 disabled:opacity-30 disabled:cursor-default transition-colors rounded"
            title="Clear chat"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <StatusDot status={status} />
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
        {messages.length === 0 && (
          <p className="text-xs text-zinc-400 text-center mt-10 px-2 leading-relaxed">
            Ask anything — record a transaction, check balances, or send a bank statement.
          </p>
        )}

        {messages.map(msg => (
          msg.proposal
            ? (
              <ProposalCard
                key={msg.id}
                proposal={msg.proposal}
                display={msg.proposalDisplay ?? ''}
                disabled={msg.streaming}
                onAction={action => {
                  if (action === 'confirm') {
                    send(buildConfirmMessage(msg.proposal))
                  } else if (action === 'decline') {
                    send('decline')
                  } else {
                    send(action)
                  }
                }}
              />
            )
            : <MessageBubble key={msg.id} message={msg} />
        ))}

        {showDots && <TypingDots label={progressLabel} />}

        {status === 'error' && (
          <div className="flex items-center gap-1.5 text-xs text-red-400">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            Connection lost — reconnecting…
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-zinc-100 px-3 py-3 shrink-0">
        <div className="flex items-end gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="shrink-0 p-1.5 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 rounded-lg transition-colors"
            title="Attach image or PDF"
          >
            <Paperclip className="w-4 h-4" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,.pdf"
            className="hidden"
            onChange={e => {
              const f = e.target.files?.[0]
              if (f) sendFile(f)
              e.target.value = ''
            }}
          />
          <textarea
            rows={1}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send(input)
              }
            }}
            placeholder="Type a message…"
            className="flex-1 resize-none text-sm border border-zinc-200 rounded-xl px-3 py-2 text-zinc-800 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition max-h-32 overflow-y-auto font-sans"
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || status !== 'open'}
            className="shrink-0 p-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-lg transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

// ── StatusDot ──────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: WsStatus }) {
  const color =
    status === 'open' ? 'bg-emerald-400' :
    status === 'connecting' ? 'bg-amber-400 animate-pulse' :
    'bg-red-400'
  return <span className={`w-2 h-2 rounded-full ${color}`} />
}

// ── TypingDots ─────────────────────────────────────────────────────────────

function TypingDots({ label }: { label?: string }) {
  return (
    <div className="flex items-end gap-2">
      <div className="w-6 h-6 rounded-full bg-zinc-100 flex items-center justify-center shrink-0">
        <Bot className="w-3.5 h-3.5 text-zinc-500" />
      </div>
      <div className="flex items-center gap-2 bg-zinc-100 rounded-2xl rounded-bl-sm px-3 py-2.5">
        <div className="flex items-center gap-1">
          <span
            className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce"
            style={{ animationDelay: '0ms' }}
          />
          <span
            className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce"
            style={{ animationDelay: '150ms' }}
          />
          <span
            className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce"
            style={{ animationDelay: '300ms' }}
          />
        </div>
        {label && <span className="text-xs text-zinc-500 truncate max-w-[140px]">{label}</span>}
      </div>
    </div>
  )
}

// ── MessageBubble ──────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex items-end gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
        isUser ? 'bg-blue-100' : 'bg-zinc-100'
      }`}>
        {isUser
          ? <User className="w-3.5 h-3.5 text-blue-600" />
          : <Bot className="w-3.5 h-3.5 text-zinc-500" />
        }
      </div>
      <div className={`max-w-[85%] px-3 py-2 rounded-2xl text-sm leading-relaxed break-words ${
        isUser
          ? 'bg-blue-600 text-white rounded-br-sm'
          : 'bg-zinc-100 text-zinc-800 rounded-bl-sm'
      }`}>
        {isUser ? (
          <span className="whitespace-pre-wrap">{message.content}</span>
        ) : (
          <>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="my-1 leading-relaxed">{children}</p>,
                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                em: ({ children }) => <em className="italic">{children}</em>,
                h1: ({ children }) => <h1 className="font-semibold text-base my-1">{children}</h1>,
                h2: ({ children }) => <h2 className="font-semibold text-sm my-1">{children}</h2>,
                h3: ({ children }) => <h3 className="font-semibold text-sm my-1">{children}</h3>,
                ul: ({ children }) => <ul className="my-1 pl-4 list-disc">{children}</ul>,
                ol: ({ children }) => <ol className="my-1 pl-4 list-decimal">{children}</ol>,
                li: ({ children }) => <li className="my-0.5">{children}</li>,
                code: ({ children }) => (
                  <code className="bg-zinc-200 px-1 rounded text-xs font-mono">{children}</code>
                ),
                pre: ({ children }) => (
                  <pre className="bg-zinc-200 rounded-lg p-2 text-xs font-mono overflow-x-auto my-1">{children}</pre>
                ),
                blockquote: ({ children }) => (
                  <blockquote className="border-l-2 border-zinc-300 pl-2 text-zinc-500 my-1">{children}</blockquote>
                ),
                hr: () => <hr className="my-2 border-zinc-300" />,
                a: ({ href, children }) => (
                  <a href={href} className="text-blue-600 underline" target="_blank" rel="noreferrer">{children}</a>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
            {message.streaming && (
              <span className="inline-block w-0.5 h-3 bg-zinc-500 ml-0.5 opacity-70 animate-pulse" />
            )}
          </>
        )}
      </div>
    </div>
  )
}
