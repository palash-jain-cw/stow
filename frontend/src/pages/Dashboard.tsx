import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ChevronDown, Bell, Clock, Repeat, Receipt } from "lucide-react";
import { api, queryKeys } from "../api/api";
import { refreshAllLivePrices } from "../api/prices";
import { MonoAmount } from "../components/MonoAmount";
import { TxnBadge, type TxnType } from "../components/TxnBadge";
import { EmptyState } from "../components/EmptyState";
import { txnDisplayFromEntries } from "../components/txnDisplay";
import { ChatInput } from "../components/ChatInput";
import { TransactionEntrySheet } from "../components/TransactionEntrySheet";
import type { Proposal } from "../components/ProposalCard";
import { useChatSession } from "../hooks/useChatSession";

// ── Types ──────────────────────────────────────────────────────────────────

interface FinancialYear {
	id: number;
	start_date: string;
	end_date: string;
	status: string;
	net_profit: number | null;
}

interface AccountOut {
	id: number;
	name: string;
	group_id: number;
	group_name: string;
	nature: string;
	is_archived: boolean;
	balance: number;
	investment_subtype?: string | null;
	price_source_id?: string | null;
}

interface PortfolioItemOut {
	remaining_units: number;
	current_value: number | null;
	cost_basis: number;
}

interface EntryOut {
	id: number;
	account_id: number;
	account_name: string;
	amount: number;
}

interface TransactionOut {
	id: number;
	number: string;
	type: string;
	date: string;
	narration: string;
	fy_id: number;
	entries: EntryOut[];
}

interface FdListItemOut {
	account_id: number;
	name: string;
	principal: number;
	interest_rate: number;
	maturity_date: string;
	days_to_maturity: number;
	status: string;
}

interface QueueItemOut {
	id: number;
	schedule_id: number;
	due_date: string;
	status: string;
	posted_transaction_id: number | null;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function getGreeting(): string {
	const h = new Date().getHours();
	if (h < 12) return "Good morning";
	if (h < 17) return "Good afternoon";
	return "Good evening";
}

function fyLabel(fy: FinancialYear): string {
	const start = new Date(fy.start_date).getFullYear();
	const end = new Date(fy.end_date).getFullYear();
	return `FY ${start}–${String(end).slice(2)}`;
}

function formatDate(iso: string): string {
	return new Date(iso).toLocaleDateString("en-IN", {
		day: "numeric",
		month: "short",
	});
}

function formatFullDate(iso: string): string {
	return new Date(iso).toLocaleDateString("en-IN", {
		weekday: "long",
		day: "numeric",
		month: "long",
	});
}

function computeNetWorth(accounts: AccountOut[]): number {
	return accounts
		.filter((a) => a.nature === "asset" || a.nature === "liability")
		.reduce((sum, a) => sum + a.balance, 0);
}

function applyInvestmentMarketValues(
	accounts: AccountOut[],
	portfolioById: Record<number, PortfolioItemOut[]>,
): AccountOut[] {
	return accounts.map((account) => {
		const subtype = account.investment_subtype;
		if (subtype !== "equity_mf" && subtype !== "stock") return account;
		const lots = (portfolioById[account.id] ?? []).filter(
			(l) => l.remaining_units > 0,
		);
		if (lots.length === 0) return account;
		const hasLive = lots.every((l) => l.current_value !== null);
		const balance = hasLive
			? lots.reduce((sum, l) => sum + (l.current_value ?? 0), 0)
			: lots.reduce((sum, l) => sum + l.cost_basis, 0);
		return { ...account, balance };
	});
}

function computeCash(accounts: AccountOut[]): {
	amount: number;
	count: number;
} {
	const bankAccounts = accounts.filter(
		(a) => a.group_name === "Bank Accounts" || a.group_name === "Cash-in-Hand",
	);
	return {
		amount: bankAccounts.reduce((sum, a) => sum + a.balance, 0),
		count: bankAccounts.length,
	};
}

function computeGstNet(accounts: AccountOut[]): number {
	const output = accounts
		.filter((a) => a.name.toLowerCase().includes("output"))
		.reduce((sum, a) => sum - a.balance, 0);
	const input = accounts
		.filter((a) => a.name.toLowerCase().includes("input"))
		.reduce((sum, a) => sum + a.balance, 0);
	return output - input;
}

// ── Zone header button ─────────────────────────────────────────────────────

function ZoneToggle({
	icon,
	iconBg,
	iconColor,
	label,
	badge,
	meta,
	open,
	onToggle,
}: {
	icon: React.ReactNode;
	iconBg: string;
	iconColor: string;
	label: string;
	badge?: number;
	meta?: string;
	open: boolean;
	onToggle: () => void;
}) {
	return (
		<button
			onClick={onToggle}
			className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-zinc-50 transition-colors"
		>
			<div className="flex items-center gap-3">
				<div
					className={`w-8 h-8 rounded-full ${iconBg} flex items-center justify-center shrink-0`}
				>
					<span className={iconColor}>{icon}</span>
				</div>
				<div className="flex items-center gap-2">
					<span className="text-sm font-medium text-zinc-800">{label}</span>
					{badge !== undefined && badge > 0 && (
						<span className="text-xs font-semibold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">
							{badge}
						</span>
					)}
					{meta && <span className="text-xs text-zinc-400">{meta}</span>}
				</div>
			</div>
			<ChevronDown
				className={`w-4 h-4 text-zinc-400 transition-transform duration-250 ${open ? "rotate-180" : ""}`}
			/>
		</button>
	);
}

// ── Metrics Strip ──────────────────────────────────────────────────────────

function MetricsStrip({
	netWorth,
	cash,
	gstNet,
}: {
	netWorth: number;
	cash: { amount: number; count: number };
	gstNet: number;
}) {
	return (
		<div className="grid grid-cols-3 gap-3">
			{/* Net Worth */}
			<div className="bg-white rounded-xl border border-zinc-200 p-4">
				<p className="text-xs text-zinc-400">Net Worth</p>
				<MonoAmount
					amount={netWorth}
					className="text-lg font-bold mt-1 text-zinc-900"
				/>
				<p className="text-[10px] text-zinc-400 mt-1">All-time position</p>
			</div>

			{/* Cash */}
			<div className="bg-white rounded-xl border border-zinc-200 p-4">
				<p className="text-xs text-zinc-400">Cash</p>
				<MonoAmount
					amount={cash.amount}
					className="text-lg font-bold mt-1 text-zinc-900"
				/>
				<p className="text-[10px] text-zinc-400 mt-1">
					{cash.count} account{cash.count !== 1 ? "s" : ""}
				</p>
			</div>

			{/* GST / Quick status */}
			<div
				className={`bg-white rounded-xl border p-4 ${gstNet > 0 ? "border-amber-200" : "border-zinc-200"}`}
			>
				<p className="text-xs text-zinc-400">
					{gstNet > 0 ? "GST Payable" : "Status"}
				</p>
				{gstNet > 0 ? (
					<>
						<MonoAmount
							amount={gstNet}
							className="text-lg font-bold mt-1 text-amber-600"
						/>
						<p className="text-[10px] text-amber-500 mt-1">Outstanding</p>
					</>
				) : (
					<>
						<p className="text-lg font-bold mt-1 text-emerald-600">Clear</p>
						<p className="text-[10px] text-zinc-400 mt-1">Nothing pending</p>
					</>
				)}
			</div>
		</div>
	);
}

// ── Attention Zone ─────────────────────────────────────────────────────────

function AttentionZone({
	open,
	onToggle,
	fds,
	recurring,
	gstNet,
}: {
	open: boolean;
	onToggle: () => void;
	fds: FdListItemOut[];
	recurring: QueueItemOut[];
	gstNet: number;
}) {
	const navigate = useNavigate();
	const total = fds.length + recurring.length + (gstNet > 0 ? 1 : 0);

	return (
		<div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
			<ZoneToggle
				icon={<Bell className="w-4 h-4" />}
				iconBg="bg-amber-50"
				iconColor="text-amber-500"
				label="Needs attention"
				badge={total}
				open={open}
				onToggle={onToggle}
			/>
			<div
				className="grid transition-all duration-300 ease-in-out"
				style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
			>
				<div className="overflow-hidden">
					{total === 0 ? (
						<p className="px-5 pb-4 text-sm text-zinc-400">
							All clear — nothing needs your attention.
						</p>
					) : (
						<div className="px-5 pb-4 space-y-2">
							{fds.map((fd) => (
								<div
									key={fd.account_id}
									className="flex items-center justify-between p-3.5 rounded-xl bg-amber-50 border border-amber-100"
								>
									<div className="flex items-center gap-3">
										<Clock className="w-4 h-4 text-amber-500 shrink-0" />
										<div>
											<p className="text-sm font-medium text-amber-900">
												{fd.name} matures in {fd.days_to_maturity} day
												{fd.days_to_maturity !== 1 ? "s" : ""}
											</p>
											<p className="text-xs text-amber-600 font-mono mt-0.5">
												<MonoAmount
													amount={fd.principal}
													colored={false}
													className="text-amber-600"
												/>
												{" · due "}
												{formatDate(fd.maturity_date)}
											</p>
										</div>
									</div>
									<button
										onClick={() => navigate("/portfolio")}
										className="text-xs text-amber-700 font-medium hover:text-amber-900 whitespace-nowrap"
									>
										View →
									</button>
								</div>
							))}

							{recurring.map((item) => (
								<div
									key={item.id}
									className="flex items-center justify-between p-3.5 rounded-xl bg-blue-50 border border-blue-100"
								>
									<div className="flex items-center gap-3">
										<Repeat className="w-4 h-4 text-blue-500 shrink-0" />
										<div>
											<p className="text-sm font-medium text-blue-900">
												Recurring transaction due today
											</p>
											<p className="text-xs text-blue-500 mt-0.5">
												Due {formatDate(item.due_date)}
											</p>
										</div>
									</div>
									<button
										onClick={() => navigate("/transactions")}
										className="text-xs text-blue-700 font-medium hover:text-blue-900 whitespace-nowrap"
									>
										Review →
									</button>
								</div>
							))}

							{gstNet > 0 && (
								<div className="flex items-center justify-between p-3.5 rounded-xl bg-violet-50 border border-violet-100">
									<div className="flex items-center gap-3">
										<Receipt className="w-4 h-4 text-violet-500 shrink-0" />
										<div>
											<p className="text-sm font-medium text-violet-900">
												GST net payable
											</p>
											<p className="text-xs text-violet-500 font-mono mt-0.5">
												<MonoAmount
													amount={gstNet}
													colored={false}
													className="text-violet-600"
												/>
											</p>
										</div>
									</div>
									<button
										onClick={() => navigate("/transactions")}
										className="text-xs text-violet-700 font-medium hover:text-violet-900 whitespace-nowrap"
									>
										Record it →
									</button>
								</div>
							)}
						</div>
					)}
				</div>
			</div>
		</div>
	);
}

// ── Recent Zone ────────────────────────────────────────────────────────────

function RecentZone({
	open,
	onToggle,
	transactions,
}: {
	open: boolean;
	onToggle: () => void;
	transactions: TransactionOut[];
}) {
	const navigate = useNavigate();
	const latest = transactions[0];

	const meta = latest
		? `last added ${formatDate(latest.date)} · ${transactions.length} total`
		: undefined;

	return (
		<div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
			<ZoneToggle
				icon={<Clock className="w-4 h-4" />}
				iconBg="bg-zinc-100"
				iconColor="text-zinc-500"
				label="Recent activity"
				meta={meta}
				open={open}
				onToggle={onToggle}
			/>
			<div
				className="grid transition-all duration-300 ease-in-out"
				style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
			>
				<div className="overflow-hidden">
					{transactions.length === 0 ? (
						<div className="px-5 pb-6">
							<EmptyState
								icon={Clock}
								heading="Your ledger is patiently waiting."
								subtext="Add your first transaction to see it here."
							/>
						</div>
					) : (
						<>
							<div className="divide-y divide-zinc-50">
								{transactions.slice(0, 10).map((txn) => {
									const { amount: displayAmt, colored } = txnDisplayFromEntries(
										txn.type,
										txn.entries,
									);
									return (
										<div
											key={txn.id}
											onClick={() => navigate("/transactions")}
											className="flex items-center justify-between px-5 py-3 hover:bg-zinc-50 cursor-pointer transition-colors"
										>
											<div className="flex items-center gap-3 min-w-0">
												<span className="text-xs text-zinc-400 w-12 shrink-0">
													{formatDate(txn.date)}
												</span>
												<div className="min-w-0">
													<p className="text-sm text-zinc-800 truncate">
														{txn.narration}
													</p>
													<p className="text-xs text-zinc-400 truncate">
														{txn.entries.find((e: EntryOut) => e.amount > 0)
															?.account_name ??
															txn.entries[0]?.account_name ??
															"—"}
													</p>
												</div>
											</div>
											<div className="flex items-center gap-3 shrink-0 ml-3">
												<TxnBadge type={txn.type as TxnType} />
												<MonoAmount
													amount={displayAmt}
													colored={colored}
													className="text-sm w-24 text-right"
												/>
											</div>
										</div>
									);
								})}
							</div>
							<div className="px-5 py-3 border-t border-zinc-100">
								<button
									onClick={() => navigate("/transactions")}
									className="text-xs text-blue-600 hover:text-blue-700"
								>
									See all transactions →
								</button>
							</div>
						</>
					)}
				</div>
			</div>
		</div>
	);
}

// ── Dashboard ──────────────────────────────────────────────────────────────

export default function Dashboard() {
	const qc = useQueryClient();
	const [openZone, setOpenZone] = useState<"attention" | "recent" | null>(null);
	const [chatExpanded, setChatExpanded] = useState(false);
	const [sheetOpen, setSheetOpen] = useState(false);
	const [editingProposal, setEditingProposal] = useState<Proposal | null>(null);
	const session = useChatSession();

	const toggle = (zone: "attention" | "recent") =>
		setOpenZone((prev) => (prev === zone ? null : zone));

	// Live price polling — refresh every 5 minutes
	useEffect(() => {
		refreshAllLivePrices();
		const interval = setInterval(refreshAllLivePrices, 5 * 60 * 1000);
		return () => clearInterval(interval);
	}, []);

	// Queries
	const { data: fys = [] } = useQuery({
		queryKey: queryKeys.financialYears.all(),
		queryFn: () => api.get<FinancialYear[]>("/financial-years"),
	});
	const activeFy = fys.find((fy) => fy.status === "active");

	const { data: positionAccounts = [] } = useQuery({
		queryKey: queryKeys.accounts.list("position"),
		queryFn: () => api.get<AccountOut[]>("/accounts?scope=position"),
		staleTime: 30_000,
	});

	const investmentAccounts = positionAccounts.filter(
		(a) =>
			a.investment_subtype === "equity_mf" || a.investment_subtype === "stock",
	);

	const { data: portfolioById = {} } = useQuery({
		queryKey: ["dashboard", "portfolios", investmentAccounts.map((a) => a.id)],
		queryFn: async () => {
			if (investmentAccounts.some((a) => a.price_source_id)) {
				await refreshAllLivePrices();
			}
			const pairs = await Promise.all(
				investmentAccounts.map(async (account) => {
					const lots = await api.get<PortfolioItemOut[]>(
						`/investments/${account.id}/portfolio`,
					);
					return [account.id, lots] as const;
				}),
			);
			return Object.fromEntries(pairs) as Record<number, PortfolioItemOut[]>;
		},
		enabled: investmentAccounts.length > 0,
		staleTime: 30_000,
	});

	const netWorthAccounts = applyInvestmentMarketValues(
		positionAccounts,
		portfolioById,
	);

	const { data: transactions = [] } = useQuery({
		queryKey: queryKeys.transactions.list(),
		queryFn: () => api.get<TransactionOut[]>("/transactions"),
	});

	const { data: recurringDue = [] } = useQuery({
		queryKey: queryKeys.recurring.dueToday(),
		queryFn: () => api.get<QueueItemOut[]>("/recurring/due-today"),
	});

	const { data: fdsMaturing = [] } = useQuery({
		queryKey: ["investments", "fds", "maturing"],
		queryFn: () =>
			api.get<FdListItemOut[]>("/investments/fds/maturing-soon?days=30"),
	});

	// Computed
	const netWorth = computeNetWorth(netWorthAccounts);
	const { amount: cashAmount, count: bankCount } =
		computeCash(netWorthAccounts);
	const gstNet = computeGstNet(netWorthAccounts);

	const recentTxns = [...transactions].sort((a, b) =>
		b.date.localeCompare(a.date),
	);

	// When chat is expanded, hide metrics/attention/recent (Option A)
	const showDashboardContent = !chatExpanded;

	return (
		<div className="max-w-2xl mx-auto px-6 py-10 space-y-3">
			{/* Header */}
			<div className="flex items-center justify-between mb-8">
				<div>
					<h1 className="text-xl font-semibold text-zinc-900">
						{getGreeting()}
					</h1>
					<p className="text-sm text-zinc-400 mt-0.5">
						{formatFullDate(new Date().toISOString())}
						{activeFy && (
							<>
								{" · "}
								<span className="font-mono text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
									{fyLabel(activeFy)}
								</span>
							</>
						)}
					</p>
				</div>
			</div>

			{/* ChatInput — the hero, always visible */}
			<ChatInput
				session={session}
				onTransactionSaved={() => {
					qc.invalidateQueries({ queryKey: queryKeys.transactions.list() });
					qc.invalidateQueries({
						queryKey: queryKeys.accounts.list("position"),
					});
				}}
				onModeChange={(expanded) => setChatExpanded(expanded)}
				onEditProposal={(proposal) => {
					setEditingProposal(proposal);
					setSheetOpen(true);
				}}
			/>

			{/* Metrics + zones — hidden when chat is expanded */}
			{showDashboardContent && (
				<>
					{/* Metrics Strip */}
					<MetricsStrip
						netWorth={netWorth}
						cash={{ amount: cashAmount, count: bankCount }}
						gstNet={gstNet}
					/>

					{/* Needs attention */}
					<AttentionZone
						open={openZone === "attention"}
						onToggle={() => toggle("attention")}
						fds={fdsMaturing}
						recurring={recurringDue}
						gstNet={gstNet}
					/>

					{/* Recent activity */}
					<RecentZone
						open={openZone === "recent"}
						onToggle={() => toggle("recent")}
						transactions={recentTxns}
					/>
				</>
			)}

			{/* Transaction entry sheet for editing proposals */}
			{editingProposal && (
				<TransactionEntrySheet
					open={sheetOpen}
					onClose={() => setSheetOpen(false)}
					prefill={{
						type: editingProposal.type as
							| "payment"
							| "receipt"
							| "journal"
							| "contra",
						amountRupees: String((editingProposal.amount_paise || 0) / 100),
						narration: editingProposal.narration ?? "",
						date: editingProposal.date,
						fromAccountId: editingProposal.from_account_id,
						toAccountId: editingProposal.to_account_id,
						tags: (editingProposal.tags ?? []) as string[],
						repeat: "none" as const,
						repeatDay: 1,
						repeatUntil: "",
					}}
					onSaved={(draft) => {
						setSheetOpen(false);
						setEditingProposal(null);
						session.sendTransaction({
							type: draft.type,
							amount_paise:
								Math.round(parseFloat(draft.amountRupees) * 100) || 0,
							narration: draft.narration,
							date: draft.date,
							from_account_id: draft.fromAccountId || 0,
							to_account_id: draft.toAccountId || undefined,
							tags: (draft.tags as string[] | undefined) ?? [],
						});
						qc.invalidateQueries({
							queryKey: queryKeys.accounts.list("position"),
						});
					}}
				/>
			)}
		</div>
	);
}
