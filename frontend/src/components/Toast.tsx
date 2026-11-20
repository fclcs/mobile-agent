import { useEffect, useState } from 'react';
import { CheckCircle, XCircle, AlertCircle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastProps {
  message: string;
  type?: ToastType;
  duration?: number;
  onClose?: () => void;
}

const iconMap = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertCircle,
  info: Info,
};

const colorMap = {
  success: 'bg-[#E3F5E7] border-[#C3E9CC] text-[#1F7A34]',
  error: 'bg-[#F8DAD7] border-[#EFC2BE] text-[#8E2A2D]',
  warning: 'bg-[#FBF7E4] border-[#F6E5A8] text-[#7A5108]',
  info: 'bg-[#FDF1DC] border-[#F5DCB4] text-[#A9690F]',
};

const iconColorMap = {
  success: 'text-[#3FB950]',
  error: 'text-[#E5484D]',
  warning: 'text-[#E0A02F]',
  info: 'text-[#F2A33A]',
};

export function Toast({ message, type = 'info', duration = 3000, onClose }: ToastProps) {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      onClose?.();
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const Icon = iconMap[type];

  return (
    <div
      className={`
        fixed top-4 right-4 z-50 
        flex items-center gap-3 px-4 py-2.5 
        bg-white border rounded-lg 
        shadow-md
        transform transition-all duration-200
        ${isVisible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}
        ${colorMap[type]}
      `}
    >
      <Icon className={`w-4 h-4 ${iconColorMap[type]}`} />
      <span className="text-sm font-medium">{message}</span>
      <button
        onClick={() => {
          setIsVisible(false);
          onClose?.();
        }}
        className="ml-2 p-1 hover:bg-black/5 rounded-lg transition-all duration-200"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

// Toast Manager for multiple toasts
interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

interface ToastManagerProps {
  toasts: ToastItem[];
  removeToast: (id: string) => void;
}

export function ToastManager({ toasts, removeToast }: ToastManagerProps) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          duration={toast.duration}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </div>
  );
}
