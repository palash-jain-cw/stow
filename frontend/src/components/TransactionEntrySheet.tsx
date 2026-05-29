import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
	ChevronDown,
	Plus,
	Paperclip,
	CheckCircle,
	AlertCircle,
	X,
	ChevronUp,
} from "lucide-react";
import { Sheet } from "./Sheet";
import { Tooltip } from "./Tooltip";
import { AccountCombobox } from "./AccountCombobox";
import { AccountSelect } from "./AccountSelect";
import { api, queryKeys } from "../api/api";
import { formatFyLabel, resolveFyForDate } from "./fyHelpers";

// ── Types ──────────────────────────────────────────────────────────────────

type TxnType = "payment" | "receipt" | "journal" | "contra";
type RepeatFreq = "none" | "daily" | "weekly" | "monthly" | "yearly";

export interface TransactionDraft {
	type: TxnType;
	amountRupees: string;
	narration: string;
	date: string;
	fromAccountId: number | null;
	toAccountId: number | null;
	tags: string[];
	repeat: RepeatFreq;
	repeatDay: number;
	repeatUntil: string;
}

interface AccountOut {
	id: number;
	name: string;
	nature: string;
	group_name: string;
}

interface EntryOut {
	id: number | null;
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
	tags: string[] | null;
	entries: EntryOut[];
}

interface FinancialYear {
	id: number;
	start_date: string;
	end_date: string;
	status: string;
}

interface JournalEntry {
	accountId: number | null;
	dr: string;
	cr: string;
}

interface Props {
	open: boolean;
	onClose: () => void;
	prefill?: Partial<TransactionDraft>;
	editTxn?: TransactionOut;
	onSaved: (tx: TransactionDraft) => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function today(): string {
	return new Date().toISOString().slice(0, 10);
}

function rupeesToPaise(s: string): number {
	return Math.round(parseFloat(s || "0") * 100);
}

function emptyDraft(prefill?: Partial<TransactionDraft>): TransactionDraft {
	return {
		type: "payment",
		amountRupees: "",
		narration: "",
		date: today(),
		fromAccountId: null,
		toAccountId: null,
		tags: [],
		repeat: "none",
		repeatDay: 1,
		repeatUntil: "",
		...prefill,
	};
}

const TYPE_LABELS: Record<TxnType, string> = {
	payment: "Payment",
	receipt: "Receipt",
	journal: "Journal",
	contra: "Contra",
};

const FROM_LABEL: Record<TxnType, string> = {
	payment: "From account",
	receipt: "From account",
	journal: "From account",
	contra: "From account",
};

const TO_LABEL: Record<TxnType, string> = {
	payment: "To account",
	receipt: "To account",
	journal: "To account",
	contra: "To account",
};

const FROM_TOOLTIP: Record<TxnType, string> = {
	payment: "The account money is leaving — usually your bank or cash account.",
	receipt: "The income source — salary, freelance, interest, etc.",
	journal: "The account being credited.",
	contra: "The bank or cash account the money is moving out of.",
};

const TO_TOOLTIP: Record<TxnType, string> = {
	payment: "The account that receives the expense — electricity, rent, etc.",
	receipt: "The bank or cash account receiving the money.",
	journal: "The account being debited.",
	contra: "The bank or cash account the money is moving into.",
};

const REPEAT_LABELS: Record<RepeatFreq, string> = {
	none: "Does not repeat",
	daily: "Daily",
	weekly: "Weekly",
	monthly: "Monthly",
	yearly: "Yearly",
};

// ── Label component ────────────────────────────────────────────────────────

function FieldLabel({ children }: { children: React.ReactNode }) {
	return (
		<label className="block text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
			{children}
		</label>
	);
}

function inputCls() {
	return "w-full px-3.5 py-2.5 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition bg-white";
}

// ── Journal entries table ──────────────────────────────────────────────────

function JournalEntriesTable({
	entries,
	onChange,
	accounts,
}: {
	entries: JournalEntry[];
	onChange: (entries: JournalEntry[]) => void;
	accounts: AccountOut[];
}) {
	const totalDr = entries.reduce((s, e) => s + rupeesToPaise(e.dr), 0);
	const totalCr = entries.reduce((s, e) => s + rupeesToPaise(e.cr), 0);
	const diff = totalDr - totalCr;
	const balanced = totalDr > 0 && diff === 0;

	const update = (
		i: number,
		field: keyof JournalEntry,
		val: string | number | null,
	) => {
		const next = entries.map((e, idx) =>
			idx === i ? { ...e, [field]: val } : e,
		);
		onChange(next);
	};

	return (
		<div>
			<div className="flex items-center gap-1.5 mb-2">
				<FieldLabel>Entries</FieldLabel>
				<Tooltip content="Every journal entry must have equal debits and credits. Dr increases assets/expenses; Cr increases liabilities/income." />
			</div>
			<div className="rounded-xl border border-zinc-200 overflow-hidden">
				<table className="w-full text-sm">
					<thead className="bg-zinc-50 border-b border-zinc-200">
						<tr>
							<th className="text-left px-3 py-2 text-xs font-medium text-zinc-400 w-1/2">
								Account
							</th>
							<th className="text-right px-3 py-2 text-xs font-medium text-zinc-400 w-1/4">
								Dr (₹)
							</th>
							<th className="text-right px-3 py-2 text-xs font-medium text-zinc-400 w-1/4">
								Cr (₹)
							</th>
						</tr>
					</thead>
					<tbody className="divide-y divide-zinc-100">
						{entries.map((entry, i) => (
							<tr key={i}>
								<td className="px-2 py-2">
									<AccountSelect
										value={entry.accountId}
										onChange={(id) => update(i, "accountId", id)}
										accounts={accounts}
										placeholder="Select account"
										size="sm"
										className="w-full max-w-none cursor-pointer"
									/>
								</td>
								<td className="px-2 py-2">
									<input
										type="number"
										min="0"
										placeholder="—"
										value={entry.dr}
										onChange={(e) => update(i, "dr", e.target.value)}
										className="w-full text-right text-xs font-mono border border-zinc-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
									/>
								</td>
								<td className="px-2 py-2">
									<input
										type="number"
										min="0"
										placeholder="—"
										value={entry.cr}
										onChange={(e) => update(i, "cr", e.target.value)}
										className="w-full text-right text-xs font-mono border border-zinc-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
									/>
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>

			<button
				type="button"
				onClick={() =>
					onChange([...entries, { accountId: null, dr: "", cr: "" }])
				}
				className="mt-2 flex items-center gap-1.5 text-xs text-blue-500 hover:text-blue-700 transition-colors"
			>
				<Plus className="w-3.5 h-3.5" /> Add entry
			</button>

			{totalDr > 0 || totalCr > 0 ? (
				balanced ? (
					<div className="mt-3 flex items-center gap-2 text-sm font-medium text-emerald-600">
						<CheckCircle className="w-4 h-4" /> Perfectly balanced, as all
						things should be.
					</div>
				) : (
					<div className="mt-3 flex items-center gap-2 text-sm font-medium text-red-500">
						<AlertCircle className="w-4 h-4" />
						Something doesn't add up — literally.{" "}
						{diff > 0
							? `Dr ₹${(diff / 100).toLocaleString("en-IN")} over`
							: `Cr ₹${(Math.abs(diff) / 100).toLocaleString("en-IN")} over`}
					</div>
				)
			) : null}
		</div>
	);
}

// ── Tags input ─────────────────────────────────────────────────────────────

function TagsInput({
	tags,
	onChange,
}: {
	tags: string[];
	onChange: (t: string[]) => void;
}) {
	const [input, setInput] = useState("");
	const add = () => {
		const t = input.trim().toLowerCase();
		if (t && !tags.includes(t)) onChange([...tags, t]);
		setInput("");
	};
	return (
		<div>
			<FieldLabel>Tags</FieldLabel>
			<div className="flex flex-wrap gap-2 mb-2">
				{tags.map((t) => (
					<span
						key={t}
						className="flex items-center gap-1 text-xs bg-zinc-100 text-zinc-700 px-2.5 py-1 rounded-full"
					>
						{t}
						<button
							type="button"
							onClick={() => onChange(tags.filter((x) => x !== t))}
							className="text-zinc-400 hover:text-zinc-700 ml-0.5"
						>
							<X className="w-3 h-3" />
						</button>
					</span>
				))}
			</div>
			<div className="flex gap-2">
				<input
					value={input}
					onChange={(e) => setInput(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === "Enter") {
							e.preventDefault();
							add();
						}
					}}
					placeholder="Add tag"
					className="flex-1 px-3 py-1.5 text-xs border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
				/>
				<button
					type="button"
					onClick={add}
					className="text-xs text-blue-500 hover:text-blue-700 px-2"
				>
					Add
				</button>
			</div>
		</div>
	);
}

// ── Main component ─────────────────────────────────────────────────────────

interface AccountErrors {
	fromAccount?: string;
	toAccount?: string;
}

export function TransactionEntrySheet({
	open,
	onClose,
	prefill,
	editTxn,
	onSaved,
}: Props) {
	const qc = useQueryClient();
	const isEdit = !!editTxn;

	const [draft, setDraft] = useState<TransactionDraft>(() =>
		emptyDraft(prefill),
	);
	const [moreOpen, setMoreOpen] = useState(isEdit);
	const [journalEntries, setJournalEntries] = useState<JournalEntry[]>([
		{ accountId: null, dr: "", cr: "" },
		{ accountId: null, dr: "", cr: "" },
	]);
	const [attachmentName, setAttachmentName] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [accountErrors, setAccountErrors] = useState<AccountErrors>({});

	// Reset on open
	useEffect(() => {
		if (open) {
			if (editTxn) {
				const debitEntry = editTxn.entries.find((e) => e.amount > 0);
				const creditEntry = editTxn.entries.find((e) => e.amount < 0);
				setDraft({
					type: editTxn.type as TxnType,
					amountRupees: debitEntry
						? String(Math.abs(debitEntry.amount) / 100)
						: "",
					narration: editTxn.narration,
					date: editTxn.date,
					fromAccountId: creditEntry?.account_id ?? null,
					toAccountId: debitEntry?.account_id ?? null,
					tags: editTxn.tags ?? [],
					repeat: "none",
					repeatDay: 1,
					repeatUntil: "",
				});
				setMoreOpen(true);
				if (editTxn.type === "journal") {
					setJournalEntries(
						editTxn.entries.map((e) => ({
							accountId: e.account_id,
							dr: e.amount > 0 ? String(e.amount / 100) : "",
							cr: e.amount < 0 ? String(Math.abs(e.amount) / 100) : "",
						})),
					);
				}
			} else {
				setDraft(emptyDraft(prefill));
				setMoreOpen(false);
				setJournalEntries([
					{ accountId: null, dr: "", cr: "" },
					{ accountId: null, dr: "", cr: "" },
				]);
			}
			setAttachmentName(null);
			setError(null);
			setAccountErrors({});
		}
	}, [open]);

	const set = <K extends keyof TransactionDraft>(
		k: K,
		v: TransactionDraft[K],
	) => setDraft((d) => ({ ...d, [k]: v }));

	// Data queries
	const { data: accounts = [] } = useQuery({
		queryKey: queryKeys.accounts.list(),
		queryFn: () => api.get<AccountOut[]>("/accounts"),
	});

	const { data: fys = [] } = useQuery({
		queryKey: queryKeys.financialYears.all(),
		queryFn: () => api.get<FinancialYear[]>("/financial-years"),
	});
	const activeFy = fys.find((fy) => fy.status === "active");
	const resolvedFy = resolveFyForDate(fys, draft.date);

	// Journal balance check
	const journalDr = journalEntries.reduce((s, e) => s + rupeesToPaise(e.dr), 0);
	const journalCr = journalEntries.reduce((s, e) => s + rupeesToPaise(e.cr), 0);
	const journalBalanced =
		draft.type === "journal" ? journalDr > 0 && journalDr === journalCr : true;

	const canSave =
		draft.type === "journal"
			? journalBalanced
			: !!draft.amountRupees && parseFloat(draft.amountRupees) > 0;

	const handleSave = () => {
		// Validate accounts for non-journal types
		if (draft.type !== "journal") {
			const errs: AccountErrors = {};
			if (!draft.fromAccountId) errs.fromAccount = "From account is required";
			if (!draft.toAccountId) errs.toAccount = "To account is required";
			if (errs.fromAccount || errs.toAccount) {
				setAccountErrors(errs);
				// Open the more-details panel so errors are visible
				setMoreOpen(true);
				return;
			}
		}
		setAccountErrors({});
		saveMutation.mutate();
	};

	// Save mutation
	const saveMutation = useMutation({
		mutationFn: async () => {
			let entries: { account_id: number; amount: number }[];

			if (draft.type === "journal") {
				entries = journalEntries
					.filter((e) => e.accountId && (e.dr || e.cr))
					.map((e) => ({
						account_id: e.accountId!,
						amount: e.dr ? rupeesToPaise(e.dr) : -rupeesToPaise(e.cr),
					}));
			} else {
				const paise = rupeesToPaise(draft.amountRupees);
				if (!draft.fromAccountId || !draft.toAccountId)
					throw new Error("Please select both accounts.");
				entries = [
					{ account_id: draft.fromAccountId, amount: -paise },
					{ account_id: draft.toAccountId, amount: paise },
				];
			}

			const body: Record<string, unknown> = {
				type: draft.type,
				date: draft.date,
				narration: draft.narration,
				entries,
				tags: draft.tags.length ? draft.tags : null,
			};
			if (resolvedFy) body.fy_id = resolvedFy.id;

			let txn: TransactionOut;
			if (isEdit && editTxn) {
				txn = await api.put<TransactionOut>(`/transactions/${editTxn.id}`, {
					narration: draft.narration,
					date: draft.date,
					tags: draft.tags.length ? draft.tags : null,
					entries,
				});
			} else {
				txn = await api.post<TransactionOut>("/transactions", body);
			}

			// Create recurring schedule if needed
			if (!isEdit && draft.repeat !== "none") {
				const firstDue = new Date(draft.date);
				if (draft.repeat === "monthly") {
					firstDue.setMonth(firstDue.getMonth() + 1);
					firstDue.setDate(draft.repeatDay);
				} else if (draft.repeat === "weekly") {
					firstDue.setDate(firstDue.getDate() + 7);
				} else if (draft.repeat === "yearly") {
					firstDue.setFullYear(firstDue.getFullYear() + 1);
				} else {
					firstDue.setDate(firstDue.getDate() + 1);
				}
				await api
					.post("/recurring/schedules", {
						template_transaction_id: txn.id,
						frequency: draft.repeat,
						day_of_period: draft.repeat === "monthly" ? draft.repeatDay : null,
						first_due_date: firstDue.toISOString().slice(0, 10),
						end_date: draft.repeatUntil || null,
					})
					.catch(() => {
						/* don't block on schedule failure */
					});
			}

			return txn;
		},
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: queryKeys.transactions.list() });
			qc.invalidateQueries({ queryKey: queryKeys.accounts.list() });
			onSaved(draft);
			onClose();
		},
		onError: (e: Error) => setError(e.message),
	});

	const title = isEdit ? `Edit — ${editTxn?.number}` : "New Transaction";

	return (
		<Sheet open={open} onClose={onClose} title={title}>
			<div className="space-y-5">
				{resolvedFy ? (
					resolvedFy.id !== activeFy?.id && (
						<div className="flex items-start gap-2 text-sm text-blue-800 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2">
							<AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
							<span>
								Posting to FY {formatFyLabel(resolvedFy)} (from transaction
								date)
							</span>
						</div>
					)
				) : (
					<div className="flex items-start gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
						<AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
						<span>
							No FY covers this date — a new year will be created when you save.
						</span>
					</div>
				)}

				{/* Type pills */}
				<div>
					<FieldLabel>Type</FieldLabel>
					<div className="flex gap-2 flex-wrap">
						{(["payment", "receipt", "journal", "contra"] as TxnType[]).map(
							(t) => (
								<button
									key={t}
									type="button"
									onClick={() => set("type", t)}
									className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-all ${
										draft.type === t
											? "bg-zinc-900 text-white border-zinc-900"
											: "border-zinc-200 text-zinc-600 hover:border-zinc-300"
									}`}
								>
									{TYPE_LABELS[t]}
								</button>
							),
						)}
					</div>
				</div>

				{draft.type !== "journal" ? (
					<>
						{/* Amount */}
						<div>
							<FieldLabel>Amount</FieldLabel>
							<div className="relative">
								<span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400 font-mono text-sm">
									₹
								</span>
								<input
									type="number"
									min="0"
									placeholder="0"
									value={draft.amountRupees}
									onChange={(e) => set("amountRupees", e.target.value)}
									className="w-full pl-8 pr-4 py-2.5 font-mono text-lg border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
								/>
							</div>
						</div>

						{/* Narration */}
						<div>
							<FieldLabel>Narration</FieldLabel>
							<textarea
								rows={2}
								placeholder="What was this for?"
								value={draft.narration}
								onChange={(e) => set("narration", e.target.value)}
								className={inputCls() + " resize-none"}
							/>
						</div>

						{/* Date */}
						<div>
							<FieldLabel>Date</FieldLabel>
							<input
								type="date"
								value={draft.date}
								onChange={(e) => set("date", e.target.value)}
								className={inputCls() + " cursor-pointer"}
							/>
						</div>

						{/* From account — always visible, in tab order after Date */}
						<AccountCombobox
							label={FROM_LABEL[draft.type]}
							tooltip={FROM_TOOLTIP[draft.type]}
							value={draft.fromAccountId}
							onChange={(id) => {
								set("fromAccountId", id);
								if (id)
									setAccountErrors((prev) => ({
										...prev,
										fromAccount: undefined,
									}));
							}}
							accounts={accounts}
							error={accountErrors.fromAccount}
						/>

						{/* To account — always visible, in tab order after From account */}
						<AccountCombobox
							label={TO_LABEL[draft.type]}
							tooltip={TO_TOOLTIP[draft.type]}
							value={draft.toAccountId}
							onChange={(id) => {
								set("toAccountId", id);
								if (id)
									setAccountErrors((prev) => ({
										...prev,
										toAccount: undefined,
									}));
							}}
							accounts={accounts}
							error={accountErrors.toAccount}
						/>

						{/* Tags — always visible, after To account */}
						<TagsInput tags={draft.tags} onChange={(t) => set("tags", t)} />

						{/* More details toggle */}
						{!isEdit && (
							<button
								type="button"
								onClick={() => setMoreOpen((o) => !o)}
								className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-700 transition-colors"
							>
								{moreOpen ? (
									<ChevronUp className="w-4 h-4" />
								) : (
									<ChevronDown className="w-4 h-4" />
								)}
								{moreOpen ? "Less details" : "More details"}
							</button>
						)}

						{/* More details panel — attachment & repeats */}
						<div
							className="grid transition-all duration-280 ease-in-out"
							style={{ gridTemplateRows: moreOpen ? "1fr" : "0fr" }}
						>
							<div className="overflow-hidden">
								<div className="space-y-4 pb-1">
									{/* Attachment */}
									<div>
										<FieldLabel>Attachment</FieldLabel>
										<label className="flex items-center gap-2 text-sm text-zinc-400 border border-dashed border-zinc-200 hover:border-zinc-300 hover:text-zinc-600 rounded-xl px-4 py-3 w-full cursor-pointer transition-colors">
											<Paperclip className="w-4 h-4 shrink-0" />
											{attachmentName ?? "Attach receipt or bill"}
											<input
												type="file"
												className="hidden"
												onChange={(e) =>
													setAttachmentName(e.target.files?.[0]?.name ?? null)
												}
											/>
										</label>
									</div>

									{/* Repeats */}
									<div>
										<div className="flex items-center gap-1.5 mb-2">
											<FieldLabel>Repeats</FieldLabel>
											<Tooltip content="Set up a recurring transaction. You'll get a reminder on the due date — confirm, edit, or let it auto-post by end of day." />
										</div>
										<div className="flex gap-2 flex-wrap">
											{(
												[
													"none",
													"daily",
													"weekly",
													"monthly",
													"yearly",
												] as RepeatFreq[]
											).map((f) => (
												<button
													key={f}
													type="button"
													onClick={() => set("repeat", f)}
													className={`text-xs px-2.5 py-1.5 rounded-lg border transition-all ${
														draft.repeat === f
															? "bg-zinc-900 text-white border-zinc-900"
															: "border-zinc-200 text-zinc-600 hover:border-zinc-300"
													}`}
												>
													{REPEAT_LABELS[f]}
												</button>
											))}
										</div>

										{draft.repeat !== "none" && (
											<div className="mt-3 space-y-3">
												{draft.repeat === "monthly" && (
													<div className="flex items-center gap-3">
														<label className="text-xs text-zinc-500 w-16 shrink-0">
															On day
														</label>
														<input
															type="number"
															min={1}
															max={28}
															value={draft.repeatDay}
															onChange={(e) =>
																set("repeatDay", Number(e.target.value))
															}
															className="text-xs border border-zinc-200 rounded-lg px-2.5 py-1.5 w-20 focus:outline-none focus:ring-2 focus:ring-blue-500"
														/>
														<span className="text-xs text-zinc-400">
															of the month
														</span>
													</div>
												)}
												<div className="flex items-center gap-3">
													<label className="text-xs text-zinc-500 w-16 shrink-0">
														Until
													</label>
													<input
														type="date"
														value={draft.repeatUntil}
														onChange={(e) => set("repeatUntil", e.target.value)}
														placeholder="No end date"
														className="text-xs border border-zinc-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
													/>
												</div>
												<p className="text-xs text-zinc-400 bg-zinc-50 rounded-lg px-3 py-2">
													On the due date, this will appear in your dashboard
													for review. If you don't act, it auto-posts by end of
													day.
												</p>
											</div>
										)}
									</div>
								</div>
							</div>
						</div>
					</>
				) : (
					/* Journal mode */
					<>
						<div>
							<FieldLabel>Narration</FieldLabel>
							<textarea
								rows={2}
								placeholder="What is this journal entry for?"
								value={draft.narration}
								onChange={(e) => set("narration", e.target.value)}
								className={inputCls() + " resize-none"}
							/>
						</div>
						<div>
							<FieldLabel>Date</FieldLabel>
							<input
								type="date"
								value={draft.date}
								onChange={(e) => set("date", e.target.value)}
								className={inputCls() + " cursor-pointer"}
							/>
						</div>
						<JournalEntriesTable
							entries={journalEntries}
							onChange={setJournalEntries}
							accounts={accounts}
						/>
					</>
				)}

				{error && (
					<p className="text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2">
						{error}
					</p>
				)}
			</div>

			{/* Footer — rendered via Sheet's children slot, needs to be sticky */}
			<div className="sticky bottom-0 bg-white border-t border-zinc-100 -mx-6 px-6 py-4 mt-6 flex items-center justify-between">
				<button
					type="button"
					onClick={onClose}
					className="text-sm text-zinc-400 hover:text-zinc-600 transition-colors"
				>
					Cancel
				</button>
				<div className="flex items-center gap-2">
					{!isEdit && (
						<button
							type="button"
							onClick={() => setMoreOpen((o) => !o)}
							className="text-sm text-zinc-500 border border-zinc-200 hover:border-zinc-300 px-3 py-2 rounded-lg transition-colors"
						>
							{moreOpen ? "Less details" : "More details"}
						</button>
					)}
					<button
						type="button"
						onClick={handleSave}
						disabled={!canSave || saveMutation.isPending}
						className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
					>
						{saveMutation.isPending ? "Saving…" : isEdit ? "Update" : "Save"}
					</button>
				</div>
			</div>
		</Sheet>
	);
}
