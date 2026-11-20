import { User, Bell } from 'lucide-react';

export function Header() {
  return (
    <header className="h-14 bg-[#FBF9F5] border-b border-[#E6E1D8] flex items-center justify-between px-5 fixed top-0 right-0 left-[var(--sidebar-w,14rem)] z-40">
      {/* Left: Title */}
      <div className="flex items-center gap-3">
        <h1 className="text-base font-semibold text-[#16191C] tracking-tight">Mobile Agent</h1>
        <span className="flex items-center gap-1.5 text-[12px] text-[#6B7076]">
          <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950]" />
          设备自动化调度
        </span>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        <button
          className="p-2 text-[#6B7076] hover:text-[#16191C] hover:bg-[#F0EDE6] rounded-lg transition-colors duration-150"
          title="通知"
        >
          <Bell size={18} />
        </button>
        <div className="w-8 h-8 rounded-full bg-[#F2A33A] flex items-center justify-center">
          <User size={16} className="text-[#101418]" />
        </div>
      </div>
    </header>
  );
}