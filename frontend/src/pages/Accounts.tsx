import { useState, useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
	Plus,
	Search,
	ChevronDown,
	Layers,
	ExternalLink,
	Pencil,
	Archive,
	ArchiveRestore,
} from "lucide-react";
import { api, queryKeys } from "../api/api";
import { MonoAmount } from "../components/MonoAmount";
import { EmptyState } from "../components/EmptyState";
import { AccountSheet } from "../components/AccountSheet";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccountGroup {
	id: number;
	name: string;
	nature: string;
	parent_id: number | null;
	sort_order: number;
	cash_flow_tag: string | null;
}

interface AccountOut {
	id: number;
	name: string;
	group_id: number;
	group_name: string;
	nature: string;
	is_archived: boolean;
	investment_subtype: string | null;
	depreciation_rate: number | null;
	accumulated_depreciation_account_id: number | null;
	price_source_id: string | null;
	currency: string;
	balance: number;
}

interface FinancialYear {
	id: number;
	start_date: string;
	end_date: string;
	status: string;
}

interface OpeningBalance {
	account_id: number;
	fy_id: number;
	amount: number;
}

interface LedgerRow {
	transaction_id: number;
	date: string;
	narration: string;
	amount: number;
	running_balance: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DEFAULT_GROUPS = ["Bank Accounts", "Cash-in-Hand", "Investments"];
const SEE_MORE_KEY = "stow.accounts.seeMore";

// ── Helpers ───────────────────────────────────────────────────────────────────

const NATURE_CHIP: Record<string, { bg: string; text: string }> = {
	asset: { bg: "bg-blue-100", text: "text-blue-600" },
	liability: { bg: "bg-rose-100", text: "text-rose-600" },
	equity: { bg: "bg-violet-100", text: "text-violet-600" },
	income: { bg: "bg-emerald-100", text: "text-emerald-600" },
	expense: { bg: "bg-red-100", text: "text-red-600" },
};

const INV_LABEL: Record<string, string> = {
	equity_mf: "MF",
	stock: "STK",
	fd: "FD",
	ppf: "PPF",
};

function AvatarChip({
	name,
	nature,
	size = "sm",
}: {
	name: string;
	nature: string;
	size?: "sm" | "lg";
}) {
	const colors = NATURE_CHIP[nature] ?? {
		bg: "bg-zinc-100",
		text: "text-zinc-500",
	};
	const dim =
		size === "lg"
			? "w-10 h-10 text-base rounded-xl"
			: "w-5 h-5 text-xs rounded-full";
	return (
		<div
			className={`${dim} ${colors.bg} flex items-center justify-center shrink-0 font-bold ${colors.text}`}
		>
			{name.charAt(0).toUpperCase()}
		</div>
	);
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Accounts() {
	const qc = useQueryClient();
	const [searchParams, setSearchParams] = useSearchParams();

	const { data: groups = [] } = useQuery<AccountGroup[]>({
		queryKey: queryKeys.accountGroups.all(),
		queryFn: () => api.get("/account-groups"),
	});

	const { data: accounts = [] } = useQuery<AccountOut[]>({
		queryKey: queryKeys.accounts.list(),
		queryFn: () => api.get("/accounts"),
	});

	const { data: fys = [] } = useQuery<FinancialYear[]>({
		queryKey: queryKeys.financialYears.all(),
		queryFn: () => api.get("/financial-years"),
	});

	const activeFy = fys.find((fy) => fy.status === "active");

	// Selected account via URL param
	const selectedIdParam = searchParams.get("account");
	const selectedId = selectedIdParam != null ? Number(selectedIdParam) : null;

	const [search, setSearch] = useState("");
	const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
	const [sheetAccount, setSheetAccount] = useState<
		AccountOut | undefined | null
	>(null); // null=closed, undefined=new, AccountOut=edit
	const [sheetInitialGroupId, setSheetInitialGroupId] = useState<
		number | undefined
	>();
	const [archiveConfirm, setArchiveConfirm] = useState(false);

	// Deep link: /accounts?new=investment opens the sheet with Investments pre-selected
	useEffect(() => {
		if (searchParams.get("new") !== "investment") return;
		const investmentsGroup = groups.find((g) => g.name === "Investments");
		if (!investmentsGroup) return;
		setSheetInitialGroupId(investmentsGroup.id);
		setSheetAccount(undefined);
		setSearchParams(
			(prev) => {
				const next = new URLSearchParams(prev);
				next.delete("new");
				return next;
			},
			{ replace: true },
		);
	}, [searchParams, groups, setSearchParams]);

	function openNewAccountSheet(initialGroupId?: number) {
		setSheetInitialGroupId(initialGroupId);
		setSheetAccount(undefined);
	}

	function closeAccountSheet() {
		setSheetAccount(null);
		setSheetInitialGroupId(undefined);
	}

	// "See more" state persisted in localStorage
	const [seeMore, setSeeMore] = useState<boolean>(() => {
		try {
			return localStorage.getItem(SEE_MORE_KEY) === "true";
		} catch {
			return false;
		}
	});

	function toggleSeeMore() {
		setSeeMore((prev) => {
			const next = !prev;
			try {
				localStorage.setItem(SEE_MORE_KEY, String(next));
			} catch {
				// ignore
			}
			return next;
		});
	}

	const selectedAccount = accounts.find((a) => a.id === selectedId) ?? null;

	// Opening balance (lazy — only when account selected and activeFy known)
	const { data: openingBalance } = useQuery<OpeningBalance>({
		queryKey: queryKeys.accounts.openingBalance(selectedId ?? 0),
		queryFn: () =>
			api.get(`/accounts/${selectedId}/opening-balance?fy_id=${activeFy!.id}`),
		enabled: selectedId != null && activeFy != null,
	});

	// Ledger for selected account
	const { data: ledgerData, isLoading: ledgerLoading } = useQuery<{
		account_name: string;
		opening_balance: number;
		entries: LedgerRow[];
	}>({
		queryKey: queryKeys.accounts.ledger(String(selectedId)),
		queryFn: () => api.get(`/accounts/${selectedId}/ledger`),
		enabled: selectedId != null,
	});
	const ledgerRows = ledgerData?.entries ?? [];

	// Archive / unarchive mutation
	const archiveMutation = useMutation({
		mutationFn: (account: AccountOut) =>
			api.post(
				`/accounts/${account.id}/${account.is_archived ? "unarchive" : "archive"}`,
				{},
			),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: queryKeys.accounts.list() });
			setArchiveConfirm(false);
		},
	});

	// Grouped + filtered accounts
	const groupedAccounts = useMemo(() => {
		const q = search.trim().toLowerCase();
		const sorted = [...groups].sort((a, b) => a.sort_order - b.sort_order);
		return sorted.map((group) => ({
			group,
			accounts: accounts.filter(
				(a) =>
					a.group_id === group.id && (!q || a.name.toLowerCase().includes(q)),
			),
			isDefault: DEFAULT_GROUPS.includes(group.name),
		}));
	}, [groups, accounts, search]);

	// Split into default-visible and hidden groups
	const visibleGroups = seeMore
		? groupedAccounts
		: groupedAccounts.filter(({ isDefault }) => isDefault);

	function toggleCollapse(groupId: number) {
		setCollapsed((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
	}

	function handleSelectAccount(id: number) {
		setSearchParams((prev) => {
			const next = new URLSearchParams(prev);
			next.set("account", String(id));
			return next;
		});
		setArchiveConfirm(false);
	}

	const selectedGroup = groups.find((g) => g.id === selectedAccount?.group_id);

	return (
		<div className="flex flex-col h-full overflow-hidden">
			{/* Header */}
			<header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 shrink-0">
				<h1 className="text-base font-semibold text-zinc-900">Accounts</h1>
				<button
					onClick={() => openNewAccountSheet()}
					className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-md transition-colors"
				>
					<Plus className="w-4 h-4" />
					New Account
				</button>
			</header>

			{/* Two-panel body */}
			<div className="flex-1 flex overflow-hidden">
				{/* Left: group tree */}
				<div className="w-72 shrink-0 bg-white border-r border-zinc-200 flex flex-col overflow-hidden">
					{/* Search */}
					<div className="px-3 py-3 border-b border-zinc-100 shrink-0">
						<div className="relative">
							<Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
							<input
								type="text"
								value={search}
								onChange={(e) => setSearch(e.target.value)}
								placeholder="Search accounts…"
								className="w-full pl-9 pr-3 py-2 text-sm border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
							/>
						</div>
					</div>

					{/* Tree */}
					<div className="flex-1 overflow-y-auto py-2 flex flex-col">
						<div className="flex-1">
							{visibleGroups.map(({ group, accounts: groupAccounts }) => {
								const isCollapsed = collapsed[group.id] ?? false;
								return (
									<div key={group.id}>
										<button
											onClick={() => toggleCollapse(group.id)}
											className="w-full flex items-center gap-2 px-3 py-2 hover:bg-zinc-50 transition-colors"
										>
											<ChevronDown
												className={`w-3.5 h-3.5 text-zinc-400 transition-transform duration-200 ${isCollapsed ? "-rotate-90" : ""}`}
											/>
											<span className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">
												{group.name}
											</span>
										</button>

										{!isCollapsed && groupAccounts.length > 0 && (
											<div>
												{groupAccounts.map((account) => (
													<button
														key={account.id}
														onClick={() => handleSelectAccount(account.id)}
														className={`w-full flex items-center justify-between pl-8 pr-3 py-2 text-left transition-colors ${
															selectedId === account.id
																? "bg-blue-50"
																: "hover:bg-zinc-50"
														} ${account.is_archived ? "opacity-50" : ""}`}
													>
														<div className="flex items-center gap-2 min-w-0">
															<AvatarChip
																name={account.name}
																nature={account.nature}
															/>
															<span className="text-sm text-zinc-800 truncate">
																{account.name}
															</span>
														</div>
														{account.investment_subtype ? (
															<span className="font-mono text-xs text-cyan-600 shrink-0 ml-2">
																{INV_LABEL[account.investment_subtype] ??
																	account.investment_subtype}
															</span>
														) : (
															<MonoAmount
																amount={account.balance}
																colored={false}
																className="text-xs text-zinc-500 shrink-0 ml-2"
															/>
														)}
													</button>
												))}
											</div>
										)}
									</div>
								);
							})}
						</div>

						{/* See more / See less toggle */}
						<div className="px-3 py-2 border-t border-zinc-100 shrink-0">
							<button
								onClick={toggleSeeMore}
								className="text-xs text-blue-600 hover:text-blue-700 font-medium transition-colors"
							>
								{seeMore ? "See less" : "See more"}
							</button>
						</div>
					</div>
				</div>

				{/* Right: detail / ledger pane */}
				<div className="flex-1 overflow-y-auto">
					{selectedAccount == null ? (
						<div className="flex flex-col items-center justify-center h-full">
							<EmptyState
								icon={Layers}
								heading="Pick an account to see its story."
								subtext="Or start fresh with a new one."
							/>
							<button
								onClick={() => openNewAccountSheet()}
								className="mt-4 flex items-center gap-2 border border-zinc-200 hover:border-zinc-300 text-zinc-600 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
							>
								<Plus className="w-4 h-4" />
								New Account
							</button>
						</div>
					) : (
						<div className="p-6">
							{/* Account header */}
							<div className="flex items-center justify-between mb-6">
								<div className="flex items-center gap-3">
									<AvatarChip
										name={selectedAccount.name}
										nature={selectedAccount.nature}
										size="lg"
									/>
									<div>
										<h2 className="text-lg font-semibold text-zinc-900">
											{selectedAccount.name}
										</h2>
										<span className="text-xs text-zinc-400">
											{selectedAccount.group_name} · {selectedAccount.nature}
											{selectedAccount.is_archived && " · archived"}
										</span>
									</div>
								</div>

								{/* Actions */}
								<div className="flex items-center gap-3">
									<Link
										to={`/transactions?account_id=${selectedAccount.id}`}
										className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium transition-colors"
									>
										<ExternalLink className="w-4 h-4" />
										Transactions
									</Link>
									<button
										onClick={() => {
											setSheetInitialGroupId(undefined);
											setSheetAccount(selectedAccount);
										}}
										className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-700 transition-colors"
									>
										<Pencil className="w-4 h-4" />
										Edit
									</button>
									<button
										onClick={() => setArchiveConfirm((v) => !v)}
										className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-600 transition-colors"
									>
										{selectedAccount.is_archived ? (
											<>
												<ArchiveRestore className="w-4 h-4" /> Unarchive
											</>
										) : (
											<>
												<Archive className="w-4 h-4" /> Archive
											</>
										)}
									</button>
								</div>
							</div>

							{/* Archive confirm banner */}
							{archiveConfirm && (
								<div className="rounded-xl border border-zinc-200 p-4 mb-6 space-y-3">
									<p className="text-sm text-zinc-700">
										{selectedAccount.is_archived
											? `Unarchive "${selectedAccount.name}"? It will reappear in entry sheets.`
											: `Archive "${selectedAccount.name}"? Archived accounts are hidden from entry sheets but their history is preserved.`}
									</p>
									<div className="flex gap-2">
										<button
											onClick={() => setArchiveConfirm(false)}
											className="text-sm text-zinc-400 hover:text-zinc-600 transition-colors"
										>
											Cancel
										</button>
										<button
											onClick={() => archiveMutation.mutate(selectedAccount)}
											disabled={archiveMutation.isPending}
											className="text-sm font-medium text-red-600 hover:text-red-700 transition-colors disabled:opacity-50"
										>
											{archiveMutation.isPending
												? "Working…"
												: selectedAccount.is_archived
													? "Unarchive"
													: "Archive"}
										</button>
									</div>
								</div>
							)}

							{/* Summary stats */}
							<div className="grid grid-cols-3 gap-3 mb-6">
								<div className="bg-zinc-50 rounded-xl p-4">
									<p className="text-xs text-zinc-400 mb-1">Current balance</p>
									<MonoAmount
										amount={selectedAccount.balance}
										className="text-xl font-bold"
									/>
								</div>
								{openingBalance != null && (
									<div className="bg-zinc-50 rounded-xl p-4">
										<p className="text-xs text-zinc-400 mb-1">
											Opening balance
										</p>
										<MonoAmount
											amount={openingBalance.amount}
											colored={false}
											className="text-xl font-bold text-zinc-800"
										/>
									</div>
								)}
								{selectedGroup?.cash_flow_tag && (
									<div className="bg-zinc-50 rounded-xl p-4">
										<p className="text-xs text-zinc-400 mb-1">Cash flow tag</p>
										<span className="text-sm font-medium text-zinc-800 capitalize">
											{selectedGroup.cash_flow_tag}
										</span>
									</div>
								)}
							</div>

							{/* Ledger table */}
							<div>
								<h3 className="text-sm font-semibold text-zinc-700 mb-3">
									Ledger
								</h3>

								{ledgerLoading ? (
									<div className="text-sm text-zinc-400 py-8 text-center">
										Loading…
									</div>
								) : ledgerRows.length === 0 ? (
									<div className="text-sm text-zinc-400 py-8 text-center">
										No transactions yet.
									</div>
								) : (
									<div className="overflow-x-auto rounded-xl border border-zinc-200">
										<table className="w-full text-sm">
											<thead>
												<tr className="border-b border-zinc-200 bg-zinc-50">
													<th className="text-left px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wide">
														Date
													</th>
													<th className="text-left px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wide">
														Narration
													</th>
													<th className="text-left px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wide">
														Counterpart
													</th>
													<th className="text-right px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wide">
														Amount
													</th>
													<th className="text-right px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-wide">
														Balance
													</th>
												</tr>
											</thead>
											<tbody className="divide-y divide-zinc-100">
												{ledgerRows.map((row) => (
													<tr
														key={row.transaction_id}
														className="hover:bg-zinc-50 transition-colors"
													>
														<td className="px-4 py-3 text-zinc-500 whitespace-nowrap font-mono text-xs">
															{new Date(row.date).toLocaleDateString("en-IN", {
																day: "numeric",
																month: "short",
																year: "numeric",
															})}
														</td>
														<td className="px-4 py-3 text-zinc-800 max-w-xs truncate">
															{row.narration}
														</td>
														<td className="px-4 py-3 text-zinc-400">—</td>
														<td className="px-4 py-3 text-right">
															<MonoAmount
																amount={row.amount}
																className="text-sm"
															/>
														</td>
														<td className="px-4 py-3 text-right">
															<MonoAmount
																amount={row.running_balance}
																colored={false}
																className="text-sm text-zinc-700"
															/>
														</td>
													</tr>
												))}
											</tbody>
										</table>
									</div>
								)}
							</div>
						</div>
					)}
				</div>
			</div>

			{/* New / Edit sheet */}
			<AccountSheet
				open={sheetAccount !== null}
				onClose={closeAccountSheet}
				account={
					sheetAccount === undefined ? undefined : (sheetAccount ?? undefined)
				}
				groups={groups}
				activeFyId={activeFy?.id}
				initialGroupId={sheetInitialGroupId}
				onSaved={closeAccountSheet}
			/>
		</div>
	);
}

function DetailRow({
	label,
	value,
}: {
	label: string;
	value: React.ReactNode;
}) {
	return (
		<div className="flex items-center justify-between py-2.5 border-b border-zinc-100">
			<span className="text-sm text-zinc-500">{label}</span>
			{value}
		</div>
	);
}
