import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Bot,
  FileCode,
  Workflow,
  Images,
  ListTodo,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  FileText,
  Settings,
  ShieldCheck,
  Smartphone,
} from 'lucide-react';
import { useEffect, useState } from 'react';

interface NavGroup {
  type: 'group';
  label: string;
  icon: React.ReactNode;
  children: { path: string; label: string; icon: React.ReactNode }[];
}

interface NavSingle {
  type: 'single';
  path: string;
  label: string;
  icon: React.ReactNode;
}

type NavEntry = NavSingle | NavGroup;

const navEntries: NavEntry[] = [
  { type: 'single', path: '/', label: '仪表盘', icon: <LayoutDashboard size={18} /> },
  { type: 'single', path: '/devices', label: '手机管理', icon: <Smartphone size={18} /> },
  { type: 'single', path: '/scripts', label: '脚本管理', icon: <FileCode size={18} /> },
  { type: 'single', path: '/workflows', label: '流程管理', icon: <Workflow size={18} /> },
  { type: 'single', path: '/rescue', label: '脚本救援', icon: <ShieldCheck size={18} /> },
  {
    type: 'group',
    label: '执行中心',
    icon: <ListTodo size={18} />,
    children: [
      { path: '/tasks', label: '任务管理', icon: <ListTodo size={16} /> },
      { path: '/screenshots', label: '截图记录', icon: <Images size={16} /> },
      { path: '/reports', label: '报告管理', icon: <FileText size={16} /> },
    ],
  },
  { type: 'single', path: '/settings', label: '模型配置', icon: <Settings size={18} /> },
];

const ITEM_BASE =
  'flex items-center gap-2.5 px-2.5 py-2 rounded-lg border-l-2 border-transparent transition-colors duration-150';
const ITEM_IDLE = 'text-[#9AA0A6] hover:bg-[#1A1F24] hover:text-[#F5EFE4]';
const ITEM_ACTIVE = 'border-[#F2A33A] bg-[#F2A33A]/10 text-[#F2A33A]';

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['执行中心']));

  useEffect(() => {
    document.documentElement.style.setProperty('--sidebar-w', collapsed ? '3.5rem' : '14rem');
  }, [collapsed]);

  const toggleGroup = (label: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  return (
    <aside
      className={`fixed left-0 top-0 h-full bg-[#101418] border-r border-[#1F2429] transition-all duration-200 z-50 ${
        collapsed ? 'w-14' : 'w-56'
      }`}
    >
      {/* Logo */}
      <div className="h-14 flex items-center justify-between px-3 border-b border-[#1F2429]">
        {!collapsed && (
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#F2A33A] flex items-center justify-center">
              <Bot size={18} className="text-[#101418]" />
            </div>
            <div className="leading-tight">
              <div className="font-semibold text-[#F5EFE4] text-sm">Mobile Agent</div>
              <div className="text-[10px] tracking-[0.18em] text-[#5F656B] uppercase">
                automation console
              </div>
            </div>
          </div>
        )}
        {collapsed && (
          <div className="w-8 h-8 rounded-lg bg-[#F2A33A] flex items-center justify-center mx-auto">
            <Bot size={18} className="text-[#101418]" />
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="p-2 space-y-0.5">
        {navEntries.map((entry) => {
          if (entry.type === 'single') {
            return (
              <NavLink
                key={entry.path}
                to={entry.path}
                className={({ isActive }) =>
                  `${ITEM_BASE} ${isActive ? ITEM_ACTIVE : ITEM_IDLE} ${
                    collapsed ? 'justify-center' : ''
                  }`
                }
                title={collapsed ? entry.label : undefined}
              >
                <span className="flex-shrink-0">{entry.icon}</span>
                {!collapsed && <span className="text-sm font-medium">{entry.label}</span>}
              </NavLink>
            );
          }

          const isExpanded = expandedGroups.has(entry.label);
          return (
            <div key={entry.label}>
              <button
                onClick={() => toggleGroup(entry.label)}
                className={`${ITEM_BASE} w-full ${ITEM_IDLE} ${collapsed ? 'justify-center' : ''}`}
                title={collapsed ? entry.label : undefined}
              >
                <span className="flex-shrink-0">{entry.icon}</span>
                {!collapsed && (
                  <>
                    <span className="text-sm font-medium flex-1 text-left">{entry.label}</span>
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </>
                )}
              </button>
              {!collapsed && isExpanded && (
                <div className="ml-4 mt-0.5 space-y-0.5 border-l border-[#24292F] pl-2">
                  {entry.children.map((child) => (
                    <NavLink
                      key={child.path}
                      to={child.path}
                      className={({ isActive }) =>
                        `flex items-center gap-2 px-2.5 py-1.5 rounded-lg transition-colors duration-150 ${
                          isActive
                            ? 'bg-[#F2A33A]/10 text-[#F2A33A]'
                            : 'text-[#7F858B] hover:bg-[#1A1F24] hover:text-[#F5EFE4]'
                        }`
                      }
                    >
                      <span className="flex-shrink-0">{child.icon}</span>
                      <span className="text-sm">{child.label}</span>
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Toggle Button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
        className="absolute -right-3 top-16 w-6 h-6 bg-[#16191C] rounded-full flex items-center justify-center text-[#9AA0A6] hover:text-[#F2A33A] transition-colors border border-[#2A2F35]"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>

      {/* Version */}
      {!collapsed && (
        <div className="absolute bottom-4 left-4 right-4 text-[11px] text-[#5F656B] text-center font-mono">
          v1.0.0
        </div>
      )}
    </aside>
  );
}