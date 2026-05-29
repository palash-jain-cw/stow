import { useState, useRef, useMemo, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { UploadCloud, FileText, X, Check, Zap } from "lucide-react";
import { api, queryKeys } from "../api/api";
import { MonoAmount } from "../components/MonoAmount";
import { AccountSelect } from "../components/AccountSelect";
import { findAccountGroupId } from "../components/InlineAccountSheet";
import {
	ImportReviewRow,
	type ImportRowDraft,
	type ImportRowField,
} from "../components/ImportReviewRow";
import {
	merchantPatternMatches,
	normalizeMerchantPattern,
	rowEligibleForRuleApply,
} from "../components/merchantRuleMatch";

interface MerchantRuleOut {
	id: number;
	pattern: string;
	account_id: number;
	tags: string[];
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccountOut {
	id: number;
	name: string;
	group_name: string;
	nature: string;
	is_archived: boolean;
}

interface FinancialYear {
	id: number;
	start_date: string;
	end_date: string;
	status: string;
}

interface BatchOut {
	id: number;
	filename: string;
	detected_bank: string | null;
	statement_from: string | null;
	statement_to: string | null;
	status: string;
	row_count: number;
}

interface StagingRowOut {
	id: number;
	date: string;
	amount: number;
	description: string;
	suggested_account_id: number | null;
	status: string;
	narration_override: string | null;
	tags: string[] | null;
	possible_duplicate: boolean;
	matched_transaction_id: number | null;
}

interface RowDraft extends ImportRowDraft {}

type Filter = "all" | "new" | "dup" | "matched" | "unmapped";
type Step = 1 | 2 | "done";
type RowField = ImportRowField;

interface RowFocus {
	rowId: number;
	field: RowField;
}

const REVIEW_ROW_HEIGHT = 44;
const REVIEW_OVERSCAN = 12;

// ── Constants ─────────────────────────────────────────────────────────────────

const PARSE_STEPS = [
	"Reading file…",
	"Extracting text…",
	"Identifying bank & format…",
	"Parsing transactions…",
	"Mapping accounts…",
	"Done",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function toRowDrafts(rows: StagingRowOut[]): RowDraft[] {
	return rows.map((r) => {
		const accountId = r.suggested_account_id;
		const isDuplicate = r.possible_duplicate;
		const isReconciled = r.status === "reconciled";
		let status = r.status as RowDraft["status"];
		if (status === "pending" && accountId && !isDuplicate) {
			status = "confirmed";
		}
		if (status === "pending" && isDuplicate) {
			status = "discarded";
		}
		return {
			id: r.id,
			date: r.date,
			amount: r.amount,
			description: r.description,
			possible_duplicate: isDuplicate,
			matched_transaction_id: r.matched_transaction_id,
			status,
			accountId,
			narration: r.narration_override ?? r.description,
			tags: r.tags ? r.tags.join(", ") : "",
		};
	});
}

function rowPayload(row: RowDraft) {
	return {
		status: row.status,
		suggested_account_id: row.accountId,
		narration_override: row.narration,
		tags: row.tags
			.split(",")
			.map((t) => t.trim())
			.filter(Boolean),
	};
}

function rowIsIncluded(row: RowDraft): boolean {
	return (
		row.status === "confirmed" ||
		row.status === "reconciled" ||
		(row.status === "pending" && row.accountId !== null)
	);
}

/** Align row status with import checkbox before persisting to API. */
function normalizeRowsForPost(drafts: RowDraft[]): RowDraft[] {
	return drafts.map((row) => {
		if (row.status === "reconciled") return row;
		if (rowIsIncluded(row) && row.accountId) {
			return { ...row, status: "confirmed" as const };
		}
		if (row.status !== "discarded") {
			return { ...row, status: "discarded" as const };
		}
		return row;
	});
}

function applyRuleToDrafts(
	drafts: RowDraft[],
	pattern: string,
	accountId: number,
	tags: string[],
	miscExpenseId: number | null,
	miscIncomeId: number | null,
): { drafts: RowDraft[]; appliedCount: number } {
	let appliedCount = 0;
	const next = drafts.map((row) => {
		if (!merchantPatternMatches(row.description, pattern)) return row;
		if (
			!rowEligibleForRuleApply(
				row.status,
				row.accountId,
				row.amount,
				miscExpenseId,
				miscIncomeId,
			)
		) {
			return row;
		}
		appliedCount += 1;
		return {
			...row,
			accountId,
			tags: tags.length > 0 ? tags.join(", ") : row.tags,
			status: "confirmed" as const,
		};
	});
	return { drafts: next, appliedCount };
}

const inputCls =
	"w-full min-w-0 px-2 py-1.5 text-xs border border-zinc-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-zinc-400";

function formatFileSize(bytes: number) {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
	return new Date(iso).toLocaleDateString("en-IN", {
		day: "numeric",
		month: "short",
		year: "numeric",
	});
}

function rowFieldKey(rowId: number, field: RowField) {
	return `${rowId}:${field}`;
}

function editableFields(row: RowDraft): RowField[] {
	if (row.status === "reconciled") return [];
	return ["include", "account", "narration", "tags"];
}

function isTypingTarget(target: EventTarget | null): boolean {
	if (!(target instanceof HTMLElement)) return false;
	const tag = target.tagName;
	if (tag === "TEXTAREA") return true;
	if (tag === "SELECT") return true;
	if (tag === "INPUT") {
		const type = (target as HTMLInputElement).type;
		return (
			type === "text" ||
			type === "search" ||
			type === "email" ||
			type === "number"
		);
	}
	return target.isContentEditable;
}

// ── Step indicator ────────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: Step }) {
	const steps = [
		{ n: 1, label: "Upload" },
		{ n: 2, label: "Review & post" },
	];
	return (
		<div className="flex items-center gap-2">
			{steps.map((s, i) => {
				const done =
					(typeof current === "number" && current > s.n) || current === "done";
				const active = current === s.n;
				return (
					<div key={s.n} className="flex items-center gap-2">
						{i > 0 && <div className="w-6 h-px bg-zinc-200" />}
						<div className="flex items-center gap-1.5">
							<div
								className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${done || active ? "bg-zinc-900 text-white" : "bg-zinc-200 text-zinc-400"}`}
							>
								{done ? <Check className="w-3 h-3" strokeWidth={3} /> : s.n}
							</div>
							<span
								className={`text-xs ${active ? "font-medium text-zinc-900" : done ? "text-zinc-500" : "text-zinc-400"}`}
							>
								{s.label}
							</span>
						</div>
					</div>
				);
			})}
		</div>
	);
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Import() {
	const queryClient = useQueryClient();
	const { data: accounts = [] } = useQuery<AccountOut[]>({
		queryKey: queryKeys.accounts.list(),
		queryFn: () => api.get("/accounts"),
	});

	const { data: fys = [] } = useQuery<FinancialYear[]>({
		queryKey: queryKeys.financialYears.all(),
		queryFn: () => api.get("/financial-years"),
	});

	const { data: accountGroups = [] } = useQuery<{ id: number; name: string }[]>(
		{
			queryKey: queryKeys.accountGroups.all(),
			queryFn: () => api.get("/account-groups"),
		},
	);

	const activeFy = fys.find((fy) => fy.status === "active");
	const activeAccounts = accounts.filter((a) => !a.is_archived);
	const bankGroupId = findAccountGroupId(accountGroups, "Bank Accounts");
	const miscExpenseId = useMemo(
		() =>
			activeAccounts.find(
				(a) =>
					a.name === "Miscellaneous" && a.group_name === "Indirect Expenses",
			)?.id ?? null,
		[activeAccounts],
	);
	const miscIncomeId = useMemo(
		() =>
			activeAccounts.find(
				(a) => a.name === "Miscellaneous" && a.group_name === "Indirect Income",
			)?.id ?? null,
		[activeAccounts],
	);
	const accountNameById = useMemo(
		() => Object.fromEntries(activeAccounts.map((a) => [a.id, a.name])),
		[activeAccounts],
	);

	// ── Wizard state ──────────────────────────────────────────────────────────

	const [step, setStep] = useState<Step>(1);
	const [bankAccountId, setBankAccountId] = useState<number | "">("");
	const [file, setFile] = useState<File | null>(null);
	const [uploading, setUploading] = useState(false);
	const [parseStatusIdx, setParseStatusIdx] = useState(0);
	const [uploadError, setUploadError] = useState<string | null>(null);
	const [batch, setBatch] = useState<BatchOut | null>(null);
	const [rowDrafts, setRowDrafts] = useState<RowDraft[]>([]);
	const [filter, setFilter] = useState<Filter>("all");
	const [posting, setPosting] = useState(false);
	const [postError, setPostError] = useState<string | null>(null);
	const [confirmResult, setConfirmResult] = useState<{
		posted: number;
		reconciled: number;
		skipped: number;
		serverSkipped?: Array<{ row_id: number; reason: string }>;
	} | null>(null);
	const [rowFocus, setRowFocus] = useState<RowFocus | null>(null);
	const [scrollTop, setScrollTop] = useState(0);
	const [viewportHeight, setViewportHeight] = useState(640);
	const [rulePattern, setRulePattern] = useState("");
	const [ruleAccountId, setRuleAccountId] = useState<number | "">("");
	const [ruleTags, setRuleTags] = useState("");
	const [ruleSaving, setRuleSaving] = useState(false);
	const [ruleError, setRuleError] = useState<string | null>(null);
	const [lastRuleApplyCount, setLastRuleApplyCount] = useState<number | null>(
		null,
	);

	const { data: merchantRules = [] } = useQuery<MerchantRuleOut[]>({
		queryKey: queryKeys.merchantRules.all(),
		queryFn: () => api.get<MerchantRuleOut[]>("/merchant-rules"),
		enabled: step === 2,
	});

	const fileInputRef = useRef<HTMLInputElement>(null);
	const dropZoneRef = useRef<HTMLDivElement>(null);
	const parseTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
	const tableScrollRef = useRef<HTMLDivElement>(null);
	const rowElementRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());
	const fieldElementRefs = useRef<Map<string, HTMLElement>>(new Map());
	const initialFocusDoneRef = useRef(false);
	const postButtonRef = useRef<HTMLButtonElement>(null);
	const savedPayloadsRef = useRef<Map<number, string>>(new Map());

	function storeSavedPayloads(rows: RowDraft[]) {
		const next = new Map<number, string>();
		for (const row of rows) {
			next.set(row.id, JSON.stringify(rowPayload(row)));
		}
		savedPayloadsRef.current = next;
	}

	// ── File pick ─────────────────────────────────────────────────────────────

	function pickFile(f: File) {
		if (!f.name.toLowerCase().endsWith(".pdf")) {
			setUploadError("Only PDF files are supported.");
			return;
		}
		setFile(f);
		setUploadError(null);
	}

	function handleDragOver(e: React.DragEvent) {
		e.preventDefault();
		dropZoneRef.current?.classList.add("!border-zinc-900");
	}

	function handleDragLeave() {
		dropZoneRef.current?.classList.remove("!border-zinc-900");
	}

	function handleDrop(e: React.DragEvent) {
		e.preventDefault();
		dropZoneRef.current?.classList.remove("!border-zinc-900");
		const f = e.dataTransfer.files[0];
		if (f) pickFile(f);
	}

	// ── Upload / parse ────────────────────────────────────────────────────────

	async function handleParse() {
		if (!file || bankAccountId === "") return;
		setUploading(true);
		setParseStatusIdx(0);
		setUploadError(null);

		parseTimerRef.current = setInterval(() => {
			setParseStatusIdx((i) => Math.min(i + 1, PARSE_STEPS.length - 2));
		}, 620);

		try {
			const fd = new FormData();
			fd.append("file", file);
			const result = await api.upload<BatchOut>("/imports", fd);

			clearInterval(parseTimerRef.current!);
			setParseStatusIdx(PARSE_STEPS.length - 1);

			const rows = await api.get<StagingRowOut[]>(`/imports/${result.id}/rows`);
			const drafts = toRowDrafts(rows);
			setBatch(result);
			setRowDrafts(drafts);
			storeSavedPayloads(drafts);

			setTimeout(() => {
				setStep(2);
				setUploading(false);
			}, 500);
		} catch (e) {
			clearInterval(parseTimerRef.current!);
			setUploading(false);
			setUploadError(e instanceof Error ? e.message : "Upload failed");
		}
	}

	// ── Row mutations (optimistic) ────────────────────────────────────────────

	function setRowIncludedById(rowId: number, included: boolean) {
		setRowDrafts((prev) =>
			prev.map((r) => {
				if (r.id !== rowId || r.status === "reconciled") return r;
				if (included) {
					return { ...r, status: r.accountId ? "confirmed" : "pending" };
				}
				return { ...r, status: "discarded" };
			}),
		);
	}

	function setRowAccountById(rowId: number, accountId: number | null) {
		setRowDrafts((prev) =>
			prev.map((r) => {
				if (r.id !== rowId) return r;
				const included = r.status !== "discarded";
				return {
					...r,
					accountId,
					status: !included ? "discarded" : accountId ? "confirmed" : "pending",
				};
			}),
		);
	}

	function setRowNarrationById(rowId: number, narration: string) {
		setRowDrafts((prev) =>
			prev.map((r) => (r.id === rowId ? { ...r, narration } : r)),
		);
	}

	function setRowTagsById(rowId: number, tags: string) {
		setRowDrafts((prev) =>
			prev.map((r) => (r.id === rowId ? { ...r, tags } : r)),
		);
	}

	function confirmAllMapped() {
		setRowDrafts((prev) =>
			prev.map((r) => {
				if (r.status === "reconciled" || r.status === "discarded") return r;
				if (!r.accountId) return r;
				return { ...r, status: "confirmed" as const };
			}),
		);
	}

	function skipUnmapped() {
		setRowDrafts((prev) =>
			prev.map((r) =>
				r.status === "pending" && !r.accountId
					? { ...r, status: "discarded" as const }
					: r,
			),
		);
	}

	function skipDuplicates() {
		setRowDrafts((prev) =>
			prev.map((r) =>
				r.possible_duplicate && r.status !== "reconciled"
					? { ...r, status: "discarded" as const }
					: r,
			),
		);
	}

	async function syncAllRowsBeforePost(rows: RowDraft[]) {
		if (!batch) return;
		await Promise.all(
			rows.map(async (row) => {
				await api.put(`/imports/${batch.id}/rows/${row.id}`, rowPayload(row));
				savedPayloadsRef.current.set(row.id, JSON.stringify(rowPayload(row)));
			}),
		);
	}

	// ── Derived counts ────────────────────────────────────────────────────────

	const counts = useMemo(
		() => ({
			all: rowDrafts.length,
			new: rowDrafts.filter(
				(r) => r.status === "pending" && !r.possible_duplicate,
			).length,
			dup: rowDrafts.filter((r) => r.possible_duplicate).length,
			matched: rowDrafts.filter((r) => r.status === "reconciled").length,
			unmapped: rowDrafts.filter(
				(r) =>
					r.status !== "discarded" && r.status !== "reconciled" && !r.accountId,
			).length,
			toPost: rowDrafts.filter(
				(r) => rowIsIncluded(r) && r.status !== "reconciled" && r.accountId,
			).length,
			skipped: rowDrafts.filter(
				(r) =>
					r.status === "discarded" || (r.status === "pending" && !r.accountId),
			).length,
		}),
		[rowDrafts],
	);

	const filteredRows = useMemo(() => {
		if (filter === "new")
			return rowDrafts.filter(
				(r) => r.status === "pending" && !r.possible_duplicate,
			);
		if (filter === "dup") return rowDrafts.filter((r) => r.possible_duplicate);
		if (filter === "matched")
			return rowDrafts.filter((r) => r.status === "reconciled");
		if (filter === "unmapped")
			return rowDrafts.filter(
				(r) =>
					r.status !== "discarded" && r.status !== "reconciled" && !r.accountId,
			);
		return rowDrafts;
	}, [rowDrafts, filter]);

	const registerFieldRef = useCallback(
		(rowId: number, field: RowField, el: HTMLElement | null) => {
			const key = rowFieldKey(rowId, field);
			if (el) fieldElementRefs.current.set(key, el);
			else fieldElementRefs.current.delete(key);
		},
		[],
	);

	const registerRowRef = useCallback(
		(rowId: number, el: HTMLTableRowElement | null) => {
			if (el) rowElementRefs.current.set(rowId, el);
			else rowElementRefs.current.delete(rowId);
		},
		[],
	);

	const scrollRowIntoView = useCallback((rowId: number) => {
		rowElementRefs.current
			.get(rowId)
			?.scrollIntoView({ block: "nearest", behavior: "smooth" });
	}, []);

	const focusRowField = useCallback(
		(rowId: number, field: RowField) => {
			setRowFocus({ rowId, field });
			requestAnimationFrame(() => {
				fieldElementRefs.current.get(rowFieldKey(rowId, field))?.focus();
				scrollRowIntoView(rowId);
			});
		},
		[scrollRowIntoView],
	);

	const focusAdjacentRow = useCallback(
		(delta: number, preferredField?: RowField) => {
			if (filteredRows.length === 0) return;
			const currentField = preferredField ?? rowFocus?.field ?? "account";
			const currentIdx = rowFocus
				? filteredRows.findIndex((r) => r.id === rowFocus.rowId)
				: delta > 0
					? -1
					: filteredRows.length;

			for (
				let i = currentIdx + delta;
				delta > 0 ? i < filteredRows.length : i >= 0;
				i += delta
			) {
				const row = filteredRows[i];
				const fields = editableFields(row);
				if (fields.length === 0) continue;
				const field = fields.includes(currentField)
					? currentField
					: fields.includes("account")
						? "account"
						: fields[0];
				focusRowField(row.id, field);
				return;
			}
		},
		[filteredRows, rowFocus, focusRowField],
	);

	const handleReviewFieldKeyDown = useCallback(
		(e: React.KeyboardEvent, row: RowDraft, field: RowField) => {
			if (e.altKey && e.key === "ArrowDown") {
				e.preventDefault();
				focusAdjacentRow(1, field);
				return;
			}
			if (e.altKey && e.key === "ArrowUp") {
				e.preventDefault();
				focusAdjacentRow(-1, field);
				return;
			}
			if (field === "include" && e.key === "Enter") {
				e.preventDefault();
				focusRowField(row.id, "account");
				return;
			}
			if (field === "narration" && e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				focusRowField(row.id, "tags");
				return;
			}
			if (field === "tags" && e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				focusAdjacentRow(1, "account");
			}
		},
		[focusAdjacentRow, focusRowField],
	);

	useEffect(() => {
		if (step !== 2) {
			initialFocusDoneRef.current = false;
			setRowFocus(null);
			return;
		}
		if (initialFocusDoneRef.current || filteredRows.length === 0) return;
		initialFocusDoneRef.current = true;
		const first =
			filteredRows.find(
				(r) =>
					r.status !== "reconciled" && r.status !== "discarded" && !r.accountId,
			) ?? filteredRows.find((r) => r.status !== "reconciled");
		if (first) {
			focusRowField(first.id, first.accountId ? "include" : "account");
		}
	}, [step, filteredRows, focusRowField]);

	useEffect(() => {
		if (step !== 2) return;

		function onDocumentKeyDown(e: KeyboardEvent) {
			if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
				e.preventDefault();
				postButtonRef.current?.click();
				return;
			}
			if (isTypingTarget(e.target)) return;
			if (e.key === "j" && !e.metaKey && !e.ctrlKey && !e.altKey) {
				e.preventDefault();
				focusAdjacentRow(1);
			} else if (e.key === "k" && !e.metaKey && !e.ctrlKey && !e.altKey) {
				e.preventDefault();
				focusAdjacentRow(-1);
			}
		}

		document.addEventListener("keydown", onDocumentKeyDown);
		return () => document.removeEventListener("keydown", onDocumentKeyDown);
	}, [step, focusAdjacentRow]);

	useEffect(() => {
		if (step !== 2 || !rowFocus) return;
		if (filteredRows.some((r) => r.id === rowFocus.rowId)) return;
		const first = filteredRows.find((r) => r.status !== "reconciled");
		if (first) focusRowField(first.id, "account");
		else setRowFocus(null);
	}, [step, filter, filteredRows, rowFocus, focusRowField]);

	useEffect(() => {
		const el = tableScrollRef.current;
		if (!el || step !== 2) return;
		const onScroll = () => setScrollTop(el.scrollTop);
		const ro = new ResizeObserver(() => setViewportHeight(el.clientHeight));
		onScroll();
		el.addEventListener("scroll", onScroll, { passive: true });
		ro.observe(el);
		return () => {
			el.removeEventListener("scroll", onScroll);
			ro.disconnect();
		};
	}, [step, batch?.id, filter]);

	const virtualWindow = useMemo(() => {
		const total = filteredRows.length;
		if (total === 0) {
			return { paddingTop: 0, paddingBottom: 0, visibleRows: [] as RowDraft[] };
		}
		const startIdx = Math.max(
			0,
			Math.floor(scrollTop / REVIEW_ROW_HEIGHT) - REVIEW_OVERSCAN,
		);
		const endIdx = Math.min(
			total,
			Math.ceil((scrollTop + viewportHeight) / REVIEW_ROW_HEIGHT) +
				REVIEW_OVERSCAN,
		);
		return {
			paddingTop: startIdx * REVIEW_ROW_HEIGHT,
			paddingBottom: (total - endIdx) * REVIEW_ROW_HEIGHT,
			visibleRows: filteredRows.slice(startIdx, endIdx),
		};
	}, [filteredRows, scrollTop, viewportHeight]);

	const handleIncludedChange = useCallback(
		(rowId: number, included: boolean) => {
			setRowIncludedById(rowId, included);
		},
		[],
	);

	const handleAccountChange = useCallback(
		(rowId: number, accountId: number | null) => {
			setRowAccountById(rowId, accountId);
		},
		[],
	);

	const handleNarrationCommit = useCallback(
		(rowId: number, narration: string) => {
			setRowNarrationById(rowId, narration);
		},
		[],
	);

	const handleTagsCommit = useCallback((rowId: number, tags: string) => {
		setRowTagsById(rowId, tags);
	}, []);

	const handleFocusField = useCallback((rowId: number, field: RowField) => {
		setRowFocus({ rowId, field });
	}, []);

	async function syncRowsToServer(rows: RowDraft[]) {
		if (!batch || rows.length === 0) return;
		await Promise.all(
			rows.map(async (row) => {
				await api.put(`/imports/${batch.id}/rows/${row.id}`, rowPayload(row));
				savedPayloadsRef.current.set(row.id, JSON.stringify(rowPayload(row)));
			}),
		);
	}

	async function handleAddMerchantRule() {
		if (!batch || rulePattern.trim() === "" || ruleAccountId === "") return;
		setRuleSaving(true);
		setRuleError(null);
		setLastRuleApplyCount(null);
		const tags = ruleTags
			.split(",")
			.map((t) => t.trim())
			.filter(Boolean);
		const pattern = normalizeMerchantPattern(rulePattern);
		try {
			await api.post<MerchantRuleOut>("/merchant-rules", {
				pattern: rulePattern.trim(),
				account_id: ruleAccountId,
				tags,
			});
			await queryClient.invalidateQueries({
				queryKey: queryKeys.merchantRules.all(),
			});

			const before = new Map(rowDrafts.map((r) => [r.id, r]));
			const { drafts: locallyApplied, appliedCount } = applyRuleToDrafts(
				rowDrafts,
				pattern,
				ruleAccountId,
				tags,
				miscExpenseId,
				miscIncomeId,
			);
			const changedRows = locallyApplied.filter((row) => {
				const prev = before.get(row.id);
				if (!prev) return false;
				return (
					prev.accountId !== row.accountId ||
					prev.tags !== row.tags ||
					prev.status !== row.status
				);
			});

			setRowDrafts(locallyApplied);
			await syncRowsToServer(changedRows);

			setLastRuleApplyCount(appliedCount);
			setRulePattern("");
			setRuleAccountId("");
			setRuleTags("");
		} catch (e) {
			setRuleError(
				e instanceof Error ? e.message : "Failed to save merchant rule",
			);
		} finally {
			setRuleSaving(false);
		}
	}

	const confirmCounts = useMemo(
		() => ({
			posted: rowDrafts.filter(
				(r) => rowIsIncluded(r) && r.status !== "reconciled" && r.accountId,
			).length,
			reconciled: rowDrafts.filter((r) => r.status === "reconciled").length,
			skipped: rowDrafts.filter(
				(r) => !rowIsIncluded(r) || (!r.accountId && r.status !== "reconciled"),
			).length,
			netInflow: rowDrafts
				.filter(
					(r) => rowIsIncluded(r) && r.accountId && r.status !== "reconciled",
				)
				.reduce((s, r) => s + r.amount, 0),
		}),
		[rowDrafts],
	);

	// ── Post ──────────────────────────────────────────────────────────────────

	async function handlePost() {
		if (!batch || bankAccountId === "") return;
		if (!activeFy) {
			setPostError(
				"No active financial year — activate one in Settings before posting.",
			);
			return;
		}
		setPosting(true);
		setPostError(null);
		try {
			if (document.activeElement instanceof HTMLElement) {
				document.activeElement.blur();
			}
			await new Promise<void>((resolve) =>
				requestAnimationFrame(() => resolve()),
			);

			const normalized = normalizeRowsForPost(rowDrafts);
			setRowDrafts(normalized);
			await syncAllRowsBeforePost(normalized);

			const result = await api.post<{
				posted_count: number;
				skipped_count: number;
				skipped: Array<{ row_id: number; reason: string }>;
			}>(`/imports/${batch.id}/confirm`, {
				bank_account_id: bankAccountId,
				fy_id: activeFy.id,
			});

			const reconciled = normalized.filter(
				(r) => r.status === "reconciled",
			).length;
			const uiSkipped = normalized.filter(
				(r) => r.status === "discarded",
			).length;
			setConfirmResult({
				posted: result.posted_count,
				reconciled,
				skipped: uiSkipped + result.skipped_count,
				serverSkipped: result.skipped_count > 0 ? result.skipped : undefined,
			});
			setStep("done");
		} catch (e) {
			setPostError(e instanceof Error ? e.message : "Failed to post");
		} finally {
			setPosting(false);
		}
	}

	// ── Reset ─────────────────────────────────────────────────────────────────

	function reset() {
		setStep(1);
		setBankAccountId("");
		setFile(null);
		setUploading(false);
		setParseStatusIdx(0);
		setUploadError(null);
		setBatch(null);
		setRowDrafts([]);
		setFilter("all");
		setConfirmResult(null);
		setPostError(null);
		setRowFocus(null);
		setScrollTop(0);
		setRulePattern("");
		setRuleAccountId("");
		setRuleTags("");
		setRuleError(null);
		setLastRuleApplyCount(null);
		savedPayloadsRef.current = new Map();
		initialFocusDoneRef.current = false;
	}

	// ── Render ────────────────────────────────────────────────────────────────

	return (
		<div className="flex flex-col h-full overflow-hidden">
			{/* Header */}
			<header className="h-14 bg-white border-b border-zinc-200 flex items-center px-6 gap-6 shrink-0">
				<span className="text-sm font-medium text-zinc-900">Bank Import</span>
				{step !== "done" && <StepIndicator current={step} />}
			</header>

			{/* ── Step 1: Upload ── */}
			{step === 1 && (
				<div className="flex-1 overflow-y-auto flex items-start justify-center pt-12 pb-8 px-4">
					<div className="w-full max-w-lg flex flex-col gap-6">
						{/* 1. Bank account selector */}
						<div>
							<label className="block text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
								Statement for account
							</label>
							<AccountSelect
								value={bankAccountId}
								onChange={(id) => setBankAccountId(id ?? "")}
								accounts={activeAccounts}
								placeholder="Select your bank account…"
								disabled={uploading}
								showGroupName
								groupByNature
								initialGroupId={bankGroupId}
							/>
						</div>

						{/* 2. Drop zone */}
						<div
							ref={dropZoneRef}
							onDragOver={handleDragOver}
							onDragLeave={handleDragLeave}
							onDrop={handleDrop}
							onClick={() => !uploading && fileInputRef.current?.click()}
							className={`border-2 border-dashed rounded-2xl p-10 flex flex-col items-center gap-4 transition-colors select-none ${
								uploading ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
							} ${file ? "border-zinc-900 border-solid" : "border-zinc-200 hover:border-zinc-400"}`}
						>
							<div className="w-12 h-12 rounded-full bg-zinc-100 flex items-center justify-center">
								<UploadCloud className="w-6 h-6 text-zinc-400" />
							</div>
							<div className="text-center">
								<p className="text-sm font-medium text-zinc-900">
									Drop your bank statement here
								</p>
								<p className="text-xs text-zinc-500 mt-1">
									PDF · Axis Bank, HDFC, Bank of India, AU Small Finance, Union
									Bank
								</p>
							</div>
							<span className="text-xs font-medium text-zinc-900 underline underline-offset-2">
								Browse file
							</span>
							<input
								ref={fileInputRef}
								type="file"
								accept=".pdf"
								className="hidden"
								onChange={(e) => {
									const f = e.target.files?.[0];
									if (f) pickFile(f);
								}}
							/>
						</div>

						{/* Selected file chip */}
						{file && !uploading && (
							<div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-zinc-200 bg-zinc-50">
								<div className="w-8 h-8 rounded-lg bg-zinc-200 flex items-center justify-center shrink-0">
									<FileText className="w-4 h-4 text-zinc-600" />
								</div>
								<div className="flex-1 min-w-0">
									<p className="text-sm font-medium text-zinc-900 truncate">
										{file.name}
									</p>
									<p className="text-xs text-zinc-500">
										{formatFileSize(file.size)}
									</p>
								</div>
								<button
									onClick={(e) => {
										e.stopPropagation();
										setFile(null);
									}}
									className="text-zinc-400 hover:text-zinc-700 transition-colors"
								>
									<X className="w-4 h-4" />
								</button>
							</div>
						)}

						{/* Parse button */}
						{file && !uploading && (
							<button
								onClick={handleParse}
								disabled={bankAccountId === ""}
								className="w-full py-2.5 rounded-xl bg-zinc-900 text-white text-sm font-medium hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
							>
								Parse statement
							</button>
						)}

						{/* Progress */}
						{uploading && (
							<div className="flex flex-col gap-3">
								<div className="flex items-center gap-3">
									<div className="w-5 h-5 rounded-full border-2 border-zinc-200 border-t-zinc-900 animate-spin shrink-0" />
									<p className="text-sm text-zinc-600">
										{PARSE_STEPS[parseStatusIdx]}
									</p>
								</div>
								<div className="h-1.5 rounded-full bg-zinc-100 overflow-hidden">
									<div
										className="h-full bg-zinc-900 rounded-full transition-all duration-500"
										style={{
											width: `${Math.round((parseStatusIdx / (PARSE_STEPS.length - 1)) * 100)}%`,
										}}
									/>
								</div>
							</div>
						)}

						{uploadError && (
							<p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">
								{uploadError}
							</p>
						)}
					</div>
				</div>
			)}

			{/* ── Step 2: Review & post ── */}
			{step === 2 && batch && (
				<div className="flex-1 flex flex-col overflow-hidden min-h-0">
					{/* Sub-header */}
					<div className="shrink-0 border-b border-zinc-100 px-4 py-2.5 flex items-center gap-3 flex-wrap bg-white">
						<div className="flex items-center gap-2 text-xs min-w-0">
							{batch.detected_bank && (
								<span className="font-medium text-zinc-900">
									{batch.detected_bank}
								</span>
							)}
							{batch.statement_from && batch.statement_to && (
								<span className="text-zinc-500">
									{formatDate(batch.statement_from)} –{" "}
									{formatDate(batch.statement_to)}
								</span>
							)}
						</div>
						<div className="flex items-center gap-1.5 flex-wrap ml-auto">
							{(["all", "new", "unmapped", "dup", "matched"] as Filter[]).map(
								(f) => {
									const label =
										f === "all"
											? `All ${counts.all}`
											: f === "new"
												? `New ${counts.new}`
												: f === "unmapped"
													? `Unmapped ${counts.unmapped}`
													: f === "dup"
														? `Duplicates ${counts.dup}`
														: `Matched ${counts.matched}`;
									return (
										<button
											key={f}
											onClick={() => setFilter(f)}
											className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${filter === f ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"}`}
										>
											{label}
										</button>
									);
								},
							)}
						</div>
					</div>

					{/* Bulk actions */}
					<div className="shrink-0 border-b border-zinc-100 px-4 py-2 flex items-center gap-2 flex-wrap bg-zinc-50/80">
						<button
							type="button"
							onClick={confirmAllMapped}
							className="text-xs px-2.5 py-1 rounded-lg border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-100 transition-colors"
						>
							Confirm all mapped
						</button>
						<button
							type="button"
							onClick={skipUnmapped}
							className="text-xs px-2.5 py-1 rounded-lg border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-100 transition-colors"
						>
							Skip unmapped
						</button>
						<button
							type="button"
							onClick={skipDuplicates}
							className="text-xs px-2.5 py-1 rounded-lg border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-100 transition-colors"
						>
							Skip duplicates
						</button>
						<span className="text-xs text-zinc-500 ml-auto">
							{counts.toPost} to post · {counts.skipped} skipped
						</span>
						<span className="text-[10px] text-zinc-400 hidden lg:inline whitespace-nowrap">
							Alt+↑↓ rows · Enter next field · j/k · Ctrl+Enter post
						</span>
					</div>

					{/* Table */}
					<div ref={tableScrollRef} className="flex-1 overflow-auto min-h-0">
						<table className="w-full text-sm border-collapse min-w-[960px]">
							<thead className="sticky top-0 bg-white border-b border-zinc-200 z-10 shadow-sm">
								<tr className="text-[10px] text-zinc-500 uppercase tracking-wide">
									<th className="px-3 py-2 text-left font-medium w-10">
										Import
									</th>
									<th className="px-2 py-2 text-left font-medium w-[88px]">
										Date
									</th>
									<th className="px-2 py-2 text-right font-medium w-[100px]">
										Amount
									</th>
									<th className="px-2 py-2 text-left font-medium min-w-[140px]">
										Description
									</th>
									<th className="px-2 py-2 text-left font-medium min-w-[160px]">
										Account
									</th>
									<th className="px-2 py-2 text-left font-medium min-w-[140px]">
										Narration
									</th>
									<th className="px-3 py-2 text-left font-medium min-w-[100px]">
										Tags
									</th>
								</tr>
							</thead>
							<tbody>
								{virtualWindow.paddingTop > 0 && (
									<tr
										aria-hidden="true"
										style={{ height: virtualWindow.paddingTop }}
									>
										<td colSpan={7} />
									</tr>
								)}
								{virtualWindow.visibleRows.map((row) => (
									<ImportReviewRow
										key={row.id}
										row={row}
										accounts={activeAccounts}
										isFocusedRow={rowFocus?.rowId === row.id}
										setRowRef={(el) => registerRowRef(row.id, el)}
										registerFieldRef={(field, el) =>
											registerFieldRef(row.id, field, el)
										}
										onIncludedChange={handleIncludedChange}
										onAccountChange={handleAccountChange}
										onNarrationCommit={handleNarrationCommit}
										onTagsCommit={handleTagsCommit}
										onFocusField={handleFocusField}
										onFieldKeyDown={handleReviewFieldKeyDown}
									/>
								))}
								{virtualWindow.paddingBottom > 0 && (
									<tr
										aria-hidden="true"
										style={{ height: virtualWindow.paddingBottom }}
									>
										<td colSpan={7} />
									</tr>
								)}
							</tbody>
						</table>
					</div>

					{/* Bottom bar */}
					<div className="shrink-0 border-t border-zinc-200 bg-white px-4 py-3 flex flex-col gap-3">
						<div className="flex items-center gap-4 flex-wrap text-xs text-zinc-600">
							<span>
								<strong className="text-zinc-900">
									{confirmCounts.posted}
								</strong>{" "}
								new
							</span>
							<span>
								<strong className="text-emerald-700">
									{confirmCounts.reconciled}
								</strong>{" "}
								reconciled
							</span>
							<span>
								<strong className="text-zinc-400">
									{confirmCounts.skipped}
								</strong>{" "}
								skipped
							</span>
							<span className="ml-auto flex items-center gap-1.5">
								Net inflow{" "}
								<MonoAmount
									amount={confirmCounts.netInflow}
									className="text-xs font-semibold"
								/>
							</span>
						</div>

						<div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2.5 flex flex-col gap-2">
							<div className="flex items-center gap-2">
								<Zap className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
								<p className="text-xs font-medium text-zinc-700">
									Add merchant rule
								</p>
							</div>
							<p className="text-[10px] text-zinc-500">
								Rules take priority over Miscellaneous. Text without{" "}
								<code className="font-mono bg-zinc-100 px-0.5 rounded">*</code>{" "}
								matches as substring (e.g.{" "}
								<code className="font-mono">swiggy</code> →{" "}
								<code className="font-mono">*swiggy*</code>).
							</p>
							<div className="grid grid-cols-1 sm:grid-cols-[1fr_160px_120px_auto] gap-2 items-end">
								<div>
									<label className="block text-[10px] text-zinc-500 uppercase tracking-wide mb-1">
										Pattern
									</label>
									<input
										type="text"
										value={rulePattern}
										onChange={(e) => setRulePattern(e.target.value)}
										placeholder="SWIGGY*"
										className={`${inputCls} font-mono`}
									/>
								</div>
								<div>
									<label className="block text-[10px] text-zinc-500 uppercase tracking-wide mb-1">
										Account
									</label>
									<AccountSelect
										value={ruleAccountId}
										onChange={(id) => setRuleAccountId(id ?? "")}
										accounts={activeAccounts}
										placeholder="Pick account"
										size="sm"
										className="w-full"
									/>
								</div>
								<div>
									<label className="block text-[10px] text-zinc-500 uppercase tracking-wide mb-1">
										Tags
									</label>
									<input
										type="text"
										value={ruleTags}
										onChange={(e) => setRuleTags(e.target.value)}
										placeholder="food, delivery"
										className={inputCls}
									/>
								</div>
								<button
									type="button"
									onClick={handleAddMerchantRule}
									disabled={
										ruleSaving ||
										rulePattern.trim() === "" ||
										ruleAccountId === ""
									}
									className="text-xs px-3 py-2 rounded-lg bg-zinc-900 text-white font-medium hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
								>
									{ruleSaving ? "Saving…" : "Add & apply"}
								</button>
							</div>
							{lastRuleApplyCount !== null && (
								<p className="text-[10px] text-emerald-700">
									Rule saved — applied to {lastRuleApplyCount} row
									{lastRuleApplyCount !== 1 ? "s" : ""} still on Miscellaneous
									in this import.
								</p>
							)}
							{ruleError && <p className="text-xs text-red-600">{ruleError}</p>}

							{merchantRules.length > 0 && (
								<div className="border-t border-zinc-200/80 pt-2 mt-1">
									<p className="text-[10px] font-medium text-zinc-600 uppercase tracking-wide mb-1.5">
										Saved rules ({merchantRules.length})
									</p>
									<ul className="max-h-28 overflow-y-auto flex flex-col gap-1">
										{merchantRules.map((rule) => (
											<li
												key={rule.id}
												className="text-[11px] text-zinc-700 flex items-center gap-2 min-w-0"
											>
												<span className="font-mono text-zinc-900 shrink-0">
													{rule.pattern}
												</span>
												<span className="text-zinc-400 shrink-0">→</span>
												<span className="truncate">
													{accountNameById[rule.account_id] ??
														`#${rule.account_id}`}
												</span>
												{rule.tags.length > 0 && (
													<span className="text-zinc-400 truncate ml-auto">
														{rule.tags.join(", ")}
													</span>
												)}
											</li>
										))}
									</ul>
								</div>
							)}
						</div>

						{postError && (
							<p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">
								{postError}
							</p>
						)}

						<div className="flex items-center gap-3">
							<button
								onClick={() => setStep(1)}
								className="px-4 py-2 text-sm text-zinc-600 border border-zinc-200 rounded-xl hover:bg-zinc-50 transition-colors"
							>
								Back
							</button>
							<div className="flex-1" />
							<button
								ref={postButtonRef}
								onClick={handlePost}
								disabled={
									posting ||
									bankAccountId === "" ||
									confirmCounts.posted + confirmCounts.reconciled === 0
								}
								className="px-5 py-2 text-sm font-medium text-white bg-zinc-900 rounded-xl hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
								title="Post transactions (Ctrl+Enter)"
							>
								{posting
									? "Posting…"
									: `Post ${confirmCounts.posted + confirmCounts.reconciled} transactions`}
							</button>
						</div>
					</div>
				</div>
			)}

			{/* ── Done ── */}
			{step === "done" && confirmResult && (
				<div className="flex-1 flex items-center justify-center">
					<div className="flex flex-col items-center gap-5 max-w-sm text-center">
						<div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center">
							<Check className="w-7 h-7 text-emerald-600" />
						</div>
						<div>
							<h2 className="text-base font-semibold text-zinc-900">
								{confirmResult.posted} transaction
								{confirmResult.posted !== 1 ? "s" : ""} posted
							</h2>
							<p className="text-sm text-zinc-500 mt-1">
								{confirmResult.reconciled > 0 &&
									`${confirmResult.reconciled} reconciled. `}
								{confirmResult.skipped > 0 &&
									`${confirmResult.skipped} skipped.`}
							</p>
							{confirmResult.serverSkipped &&
								confirmResult.serverSkipped.length > 0 && (
									<p className="text-xs text-amber-700 mt-2 text-left max-w-sm">
										Some rows could not be posted:{" "}
										{confirmResult.serverSkipped
											.slice(0, 3)
											.map((s) => s.reason)
											.join("; ")}
									</p>
								)}
						</div>
						<div className="flex gap-3">
							<button
								onClick={reset}
								className="px-4 py-2 text-sm text-zinc-600 border border-zinc-200 rounded-xl hover:bg-zinc-50 transition-colors"
							>
								Import another
							</button>
							<Link
								to="/transactions"
								className="px-4 py-2 text-sm font-medium text-white bg-zinc-900 rounded-xl hover:bg-zinc-700 transition-colors"
							>
								View transactions
							</Link>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
