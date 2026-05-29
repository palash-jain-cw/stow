import { useState, useRef, useEffect, useCallback } from "react";
import { ChevronDown, Send, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ProposalCard, type Proposal } from "./ProposalCard";

// ── Types ──────────────────────────────────────────────────────────────────

type ChatMode = "compact" | "expanded";

interface ChatInputProps {
	onTransactionSaved?: () => void;
	onModeChange?: (expanded: boolean) => void;
	onEditProposal?: (proposal: Proposal) => void;
	session: ReturnType<typeof import("../hooks/useChatSession").useChatSession>;
}

// ── Suggestions (shown in compact mode placeholder) ────────────────────────

const SUGGESTIONS = [
	"paid rent 15000 from HDFC",
	"received freelance payment 22500",
	"paid lunch at CCD ₹350",
	"transferred 10000 to savings",
];

function getRandomSuggestion(): string {
	return SUGGESTIONS[Math.floor(Math.random() * SUGGESTIONS.length)];
}

// ── Main Component ─────────────────────────────────────────────────────────

export function ChatInput({
	onTransactionSaved,
	onModeChange,
	onEditProposal,
	session,
}: ChatInputProps) {
	const [mode, setMode] = useState<ChatMode>("compact");
	const [inputValue, setInputValue] = useState("");
	const [suggestion] = useState(getRandomSuggestion);

	const inputRef = useRef<HTMLInputElement>(null);
	const messagesEndRef = useRef<HTMLDivElement>(null);

	// Ctrl+K to focus input
	useEffect(() => {
		const handler = (e: KeyboardEvent) => {
			if ((e.ctrlKey || e.metaKey) && e.key === "k") {
				e.preventDefault();
				if (mode === "compact") {
					setMode("expanded");
					onModeChange?.(true);
				}
				inputRef.current?.focus();
			} else if (e.key === "Escape" && mode === "expanded") {
				handleCollapse();
			}
		};
		document.addEventListener("keydown", handler);
		return () => document.removeEventListener("keydown", handler);
	}, [mode, onModeChange]);

	// Focus input when expanding
	useEffect(() => {
		if (mode === "expanded" && inputRef.current) {
			inputRef.current.focus();
		}
	}, [mode]);

	// Scroll to bottom on new messages
	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [session.messages, session.isTyping]);

	const handleSend = useCallback(
		(text: string) => {
			if (!text.trim()) return;
			session.send(text);
			setInputValue("");
			setMode("expanded");
			onModeChange?.(true);
		},
		[session, onModeChange],
	);

	const handleKeyDown = useCallback(
		(e: React.KeyboardEvent) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				if (session.isTyping) return;
				handleSend(inputValue);
			}
		},
		[inputValue, handleSend, session.isTyping],
	);

	const handleProposalAction = useCallback(
		(action: string, proposal: Proposal) => {
			if (action === "confirm") {
				session.confirmProposal(proposal);
				onTransactionSaved?.();
			} else if (action === "decline") {
				session.declineProposal();
			} else if (action === "edit") {
				onEditProposal?.(proposal);
			}
		},
		[session, onTransactionSaved],
	);

	const handleCollapse = useCallback(() => {
		setMode("compact");
		setInputValue("");
		session.clear();
		onModeChange?.(false);
	}, [session, onModeChange]);

	const hasMessages = session.messages.length > 0;
	const hasProposal = session.currentProposal !== null;

	return (
		<div
			className={`bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden transition-all duration-300 ${
				mode === "expanded" ? "rounded-b-none" : ""
			}`}
		>
			{/* ── Compact Mode ──────────────────────────────────────────── */}
			{mode === "compact" && (
				<div className="px-5 py-4">
					<div className="flex items-center gap-3 mb-3">
						<div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center shrink-0">
							<span className="text-blue-600 text-sm font-bold">✦</span>
						</div>
						<span className="text-zinc-400 text-sm">What happened?</span>
					</div>
					<div className="flex items-center gap-2">
						<input
							ref={inputRef}
							type="text"
							value={inputValue}
							onChange={(e) => setInputValue(e.target.value)}
							onKeyDown={handleKeyDown}
							placeholder={suggestion}
							className="flex-1 text-sm text-zinc-800 placeholder-zinc-300 border border-zinc-200 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
						/>
						<button
							onClick={() => handleSend(inputValue)}
							disabled={!inputValue.trim() || session.isTyping}
							className="shrink-0 p-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl transition-colors"
						>
							<Send className="w-4 h-4" />
						</button>
					</div>
					<div className="mt-2 text-center">
						<span className="text-xs text-zinc-300">Press</span>
						<span className="inline-flex items-center mx-1 text-[10px] font-mono bg-zinc-100 text-zinc-400 px-1.5 py-0.5 rounded">
							⌘K
						</span>
						<span className="text-xs text-zinc-300">to expand</span>
					</div>
				</div>
			)}

			{/* ── Expanded Mode ─────────────────────────────────────────── */}
			{mode === "expanded" && (
				<>
					{/* Header */}
					<div className="px-5 py-3 border-b border-zinc-100 flex items-center justify-between">
						<div className="flex items-center gap-2">
							{session.status === "error" ? (
								<span className="flex items-center gap-1 text-xs text-red-500">
									<span className="w-2 h-2 rounded-full bg-red-500" />
									Disconnected
									<button
										onClick={() => window.location.reload()}
										className="ml-1 text-blue-600 hover:underline"
									>
										Retry
									</button>
								</span>
							) : session.status === "connecting" ? (
								<span className="flex items-center gap-1 text-xs text-amber-500">
									<span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
									Connecting…
								</span>
							) : (
								<span className="w-2 h-2 rounded-full bg-green-500" />
							)}
							<span className="text-sm font-medium text-zinc-800">
								{hasMessages ? "Conversation" : "What happened?"}
							</span>
						</div>
						<button
							onClick={handleCollapse}
							className="p-1 text-zinc-400 hover:text-zinc-600 rounded-lg transition-colors"
						>
							<ChevronDown className="w-4 h-4" />
						</button>
					</div>

					{/* Messages */}
					<div className="px-5 py-4 space-y-4 min-h-[120px] max-h-[400px] overflow-y-auto">
						{session.messages.length === 0 ? (
							<div className="flex flex-col items-center justify-center h-32 text-center">
								<div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center mb-3">
									<span className="text-blue-600 text-lg">✦</span>
								</div>
								<p className="text-sm text-zinc-500 max-w-xs">
									I'm your financial assistant. Tell me about your transactions
									— like "paid rent 15000 from HDFC" or "received freelance
									payment 22500".
								</p>
							</div>
						) : (
							<>
								{session.messages.map((msg) => (
									<div
										key={msg.id}
										className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
									>
										{msg.role === "user" ? (
											<div className="max-w-[80%]">
												<div className="bg-blue-600 text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm">
													{msg.content}
												</div>
											</div>
										) : (
											<div className="max-w-[85%]">
												{/* Streaming text */}
												{msg.content && !msg.proposal && (
													<div className="bg-zinc-100 rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm text-zinc-800 leading-relaxed prose prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
														<ReactMarkdown remarkPlugins={[remarkGfm]}>
															{msg.content}
														</ReactMarkdown>
														{msg.streaming && (
															<span className="inline-block w-0.5 h-3 bg-zinc-500 ml-0.5 opacity-70 animate-pulse" />
														)}
													</div>
												)}

												{/* Proposal card */}
												{msg.proposal && (
													<ProposalCard
														proposal={msg.proposal}
														display={msg.proposalDisplay ?? msg.content}
														onAction={(action) =>
															handleProposalAction(action, msg.proposal!)
														}
														disabled={msg.streaming || session.isTyping}
													/>
												)}

												{/* Completed reply with no visible body */}
												{!msg.streaming &&
													!msg.proposal &&
													!msg.content.trim() && (
														<div className="bg-zinc-100 rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm text-zinc-500 italic">
															No response received.
														</div>
													)}
											</div>
										)}
									</div>
								))}
							</>
						)}

						{/* Typing indicator */}
						{session.isTyping && (
							<div className="flex items-center gap-2 text-zinc-400">
								<Loader2 className="w-4 h-4 animate-spin" />
								<span className="text-xs">
									{session.progressLabel || "Stow is thinking…"}
								</span>
							</div>
						)}

						<div ref={messagesEndRef} />
					</div>

					{/* Input */}
					<div className="px-5 py-3 border-t border-zinc-100">
						<div className="flex items-center gap-2">
							<input
								ref={inputRef}
								type="text"
								value={inputValue}
								onChange={(e) => setInputValue(e.target.value)}
								onKeyDown={handleKeyDown}
								placeholder={
									hasProposal
										? "Confirm, edit, or ask something else…"
										: "What else?"
								}
								className="flex-1 text-sm text-zinc-800 placeholder-zinc-300 border border-zinc-200 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
							/>
							<button
								onClick={() => handleSend(inputValue)}
								disabled={!inputValue.trim() || session.isTyping}
								className="shrink-0 p-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl transition-colors"
							>
								<Send className="w-4 h-4" />
							</button>
						</div>
					</div>
				</>
			)}
		</div>
	);
}
