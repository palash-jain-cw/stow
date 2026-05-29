import { useEffect, useRef } from "react";
import { X } from "lucide-react";

interface SheetProps {
	open: boolean;
	onClose: () => void;
	title?: string;
	children: React.ReactNode;
}

export function Sheet({ open, onClose, title, children }: SheetProps) {
	const sheetRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!open) return;
		const handleKey = (e: KeyboardEvent) => {
			if (e.key === "Escape") onClose();
		};
		document.addEventListener("keydown", handleKey);
		// Move focus to the sheet when it opens
		sheetRef.current?.focus();
		return () => {
			document.removeEventListener("keydown", handleKey);
		};
	}, [open, onClose]);

	if (!open) return null;

	return (
		<div className="fixed inset-0 z-50 flex">
			<div
				className="flex-1 bg-black/40"
				onClick={onClose}
				aria-hidden="true"
			/>
			<div
				ref={sheetRef}
				tabIndex={-1}
				className="w-[440px] bg-white shadow-lg h-full overflow-y-auto flex flex-col outline-none"
				role="dialog"
				aria-modal="true"
			>
				{title && (
					<div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 shrink-0">
						<h2 className="text-base font-semibold text-zinc-900">{title}</h2>
						<button
							onClick={onClose}
							className="p-1 rounded text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
							aria-label="Close"
						>
							<X className="w-4 h-4" />
						</button>
					</div>
				)}
				<div className="flex-1 px-6 py-4">{children}</div>
			</div>
		</div>
	);
}
