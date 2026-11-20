import { X } from 'lucide-react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'default';
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '确定',
  cancelLabel = '取消',
  variant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  const confirmClass =
    variant === 'danger'
      ? 'bg-[#E5484D] hover:bg-[#C93B3F]'
      : 'bg-[#F2A33A] hover:bg-[#C97F1E]';

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white border border-[#E6E1D8] rounded-lg p-5 w-full max-w-md mx-4 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-[#16191C]">{title}</h2>
          <button onClick={onCancel} className="p-1.5 hover:bg-[#F0EDE6] rounded-lg transition-all duration-200">
            <X className="w-4 h-4 text-[#6B7076]" />
          </button>
        </div>
        <p className="text-[#6B7076] text-sm mb-4">{message}</p>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 bg-[#F0EDE6] hover:bg-[#E6E1D8] text-[#6B7076] text-sm font-medium rounded-lg transition-all duration-200"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 px-4 py-2 text-white text-sm font-medium rounded-lg transition-all duration-200 ${confirmClass}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
