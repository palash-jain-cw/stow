import { useState, useRef, useCallback, useEffect } from "react";
import type { Proposal } from "../components/ProposalCard";

// ── Types ──────────────────────────────────────────────────────────────────

interface ChatMessage {
	id: string;
	role: "user" | "agent";
	content: string;
	streaming?: boolean;
	proposal?: Proposal;
	proposalDisplay?: string;
}

type WsStatus = "connecting" | "open" | "error";

interface TransactionData {
	type: "payment" | "receipt" | "journal" | "contra";
	amount_paise: number;
	narration: string;
	date: string;
	from_account_id: number;
	to_account_id?: number;
	tags?: string[];
}

interface ChatSessionReturn {
	messages: ChatMessage[];
	status: WsStatus;
	isTyping: boolean;
	progressLabel: string;
	currentProposal: Proposal | null;
	send: (text: string) => void;
	confirmProposal: (proposal: Proposal & { amount?: number }) => void;
	declineProposal: () => void;
	editProposal: (
		proposal: Proposal & { amount?: number },
		edits: Partial<Proposal>,
	) => void;
	sendTransaction: (tx: TransactionData) => Promise<void>;
	clear: () => void;
}

// ── Constants ──────────────────────────────────────────────────────────────

const PROPOSAL_PREFIX = "PROPOSAL:";
const EMPTY_REPLY =
	"I couldn't generate a response. Please try again.";
const DISCONNECT_REPLY =
	"Connection lost before the reply arrived. Please try again.";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const WS_URL = BASE.replace(/^http/, "ws") + "/chat/ws";

// ── Helpers ────────────────────────────────────────────────────────────────

function parseProposal(
	content: string,
): { proposal: Proposal; display: string } | null {
	for (const line of content.split("\n")) {
		if (line.startsWith(PROPOSAL_PREFIX)) {
			try {
				const proposal = JSON.parse(
					line.slice(PROPOSAL_PREFIX.length),
				) as Proposal;
				const display = content
					.split("\n")
					.filter((l) => !l.startsWith(PROPOSAL_PREFIX))
					.join("\n")
					.trim();
				return { proposal, display };
			} catch {
				return null;
			}
		}
	}
	return null;
}

function finalizeAgentMessage(msg: ChatMessage): ChatMessage {
	const parsed = parseProposal(msg.content);
	if (parsed) {
		return {
			...msg,
			streaming: false,
			proposal: parsed.proposal,
			proposalDisplay: parsed.display,
			content: parsed.display || msg.content,
		};
	}
	if (!msg.content.trim()) {
		return { ...msg, streaming: false, content: EMPTY_REPLY };
	}
	return { ...msg, streaming: false };
}

function buildConfirmMessage(proposal: Proposal & { amount?: number }): string {
	const payload: Record<string, unknown> = { ...proposal };
	if (!proposal.tags?.length) {
		delete payload.tags;
	}
	return `confirm:${JSON.stringify(payload)}`;
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useChatSession(): ChatSessionReturn {
	const [messages, setMessages] = useState<ChatMessage[]>([]);
	const [status, setStatus] = useState<WsStatus>("connecting");
	const [isTyping, setIsTyping] = useState(false);
	const [progressLabel, setProgressLabel] = useState("");
	const [currentProposal, setCurrentProposal] = useState<Proposal | null>(null);

	const wsRef = useRef<WebSocket | null>(null);
	const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const pendingQueueRef = useRef<string[]>([]);
	const mountedRef = useRef(true);

	const clearPendingQueue = useCallback(() => {
		pendingQueueRef.current = [];
		setIsTyping(false);
		setProgressLabel("");
	}, []);

	const finalizePendingOnDisconnect = useCallback(() => {
		const pending = [...pendingQueueRef.current];
		pendingQueueRef.current = [];
		if (pending.length === 0) {
			setIsTyping(false);
			setProgressLabel("");
			return;
		}
		setMessages((prev) =>
			prev.map((m) =>
				pending.includes(m.id) && m.streaming
					? {
							...m,
							streaming: false,
							content: m.content.trim() ? m.content : DISCONNECT_REPLY,
						}
					: m,
			),
		);
		setIsTyping(false);
		setProgressLabel("");
	}, []);

	// Connection lifecycle
	useEffect(() => {
		mountedRef.current = true;

		function connect() {
			const ws = new WebSocket(WS_URL);
			wsRef.current = ws;
			setStatus("connecting");

			ws.onopen = () => setStatus("open");

			ws.onmessage = ({ data }: MessageEvent<string>) => {
				try {
					const raw = JSON.parse(data) as {
						type: string;
						content?: string;
						label?: string;
					};

					if (raw.type === "progress") {
						setProgressLabel(raw.label ?? "");
					} else if (raw.type === "token" && raw.content !== undefined) {
						const targetId = pendingQueueRef.current[0];
						if (!targetId) return;
						setMessages((prev) =>
							prev.map((m) =>
								m.id === targetId
									? {
											...m,
											content: m.content + raw.content,
											streaming: true,
										}
									: m,
							),
						);
					} else if (raw.type === "done") {
						const doneId = pendingQueueRef.current.shift();
						if (doneId) {
							setMessages((prev) => {
								const updated = prev.map((m) =>
									m.id === doneId ? finalizeAgentMessage(m) : m,
								);
								const finalized = updated.find((m) => m.id === doneId);
								if (finalized?.proposal) {
									setCurrentProposal(finalized.proposal);
								}
								return updated;
							});
						}
						if (pendingQueueRef.current.length === 0) {
							setIsTyping(false);
							setProgressLabel("");
						}
					}
				} catch (err) {
					console.error("[useChatSession] Failed to parse WS message:", err);
				}
			};

			ws.onerror = () => {
				setStatus("error");
				finalizePendingOnDisconnect();
			};

			ws.onclose = () => {
				setStatus("error");
				finalizePendingOnDisconnect();
				if (mountedRef.current) {
					reconnectTimerRef.current = setTimeout(connect, 2000);
				}
			};
		}

		connect();
		return () => {
			mountedRef.current = false;
			if (reconnectTimerRef.current) {
				clearTimeout(reconnectTimerRef.current);
			}
			wsRef.current?.close();
		};
	}, [finalizePendingOnDisconnect]);

	// Send text message
	const send = useCallback((text: string) => {
		const ws = wsRef.current;
		if (!text.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;

		const userId = crypto.randomUUID();
		const agentId = crypto.randomUUID();
		setMessages((prev) => [
			...prev,
			{ id: userId, role: "user", content: text },
			{ id: agentId, role: "agent", content: "", streaming: true },
		]);
		pendingQueueRef.current.push(agentId);
		setIsTyping(true);
		setProgressLabel("");
		setCurrentProposal(null);
		ws.send(JSON.stringify({ type: "text", content: text }));
	}, []);

	const sendAgentAction = useCallback((payload: string) => {
		const ws = wsRef.current;
		if (!ws || ws.readyState !== WebSocket.OPEN) return;
		const agentId = crypto.randomUUID();
		setMessages((prev) => [
			...prev,
			{ id: agentId, role: "agent", content: "", streaming: true },
		]);
		pendingQueueRef.current.push(agentId);
		setIsTyping(true);
		setProgressLabel("");
		ws.send(JSON.stringify({ type: "text", content: payload }));
	}, []);

	// Confirm proposal
	const confirmProposal = useCallback(
		(proposal: Proposal & { amount?: number }) => {
			sendAgentAction(buildConfirmMessage(proposal));
		},
		[sendAgentAction],
	);

	// Decline proposal
	const declineProposal = useCallback(() => {
		sendAgentAction("decline");
	}, [sendAgentAction]);

	// Edit proposal
	const editProposal = useCallback(
		(proposal: Proposal & { amount?: number }, edits: Partial<Proposal>) => {
			const payload = { ...proposal, ...edits };
			sendAgentAction(buildConfirmMessage(payload));
		},
		[sendAgentAction],
	);

	// Clear chat
	const clear = useCallback(() => {
		setMessages([]);
		setCurrentProposal(null);
		clearPendingQueue();
	}, [clearPendingQueue]);

	// Send a transaction (from edit flow) — creates it and adds to chat
	const sendTransaction = useCallback(async (tx: TransactionData) => {
		try {
			const res = await fetch(`${BASE}/api/transactions`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(tx),
			});
			if (!res.ok) {
				const text = await res.text().catch(() => res.statusText);
				throw new Error(`${res.status}: ${text}`);
			}

			const amountRupees = (tx.amount_paise / 100).toLocaleString("en-IN", {
				minimumFractionDigits: 2,
				maximumFractionDigits: 2,
			});
			const direction = tx.type === "receipt" ? "Received" : "Paid";
			const msgId = crypto.randomUUID();
			setMessages((prev) => [
				...prev,
				{
					id: msgId,
					role: "agent",
					content: `${direction} ₹${amountRupees}${tx.narration ? ` — ${tx.narration}` : ""}`,
					streaming: false,
				},
			]);
		} catch (err) {
			console.error("[useChatSession] sendTransaction failed:", err);
			const msgId = crypto.randomUUID();
			setMessages((prev) => [
				...prev,
				{
					id: msgId,
					role: "agent",
					content: `❌ Failed to save transaction: ${err instanceof Error ? err.message : "unknown error"}`,
					streaming: false,
				},
			]);
		}
	}, []);

	return {
		messages,
		status,
		isTyping,
		progressLabel,
		currentProposal,
		send,
		confirmProposal,
		declineProposal,
		editProposal,
		sendTransaction,
		clear,
	};
}

export type { Proposal };
export type { ChatMessage };
export type { WsStatus };
